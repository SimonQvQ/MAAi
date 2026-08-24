// MAAiAgent.mm — 注入明日方舟进程的 agent 终端。
// 连接 maai-server(Docker): 主动拨号 + 自动重连；收到 JSON 帧后分发命令，
// 执行截图/触摸/浮层；按需流式推送 SCREENSHOT 事件。
// 协议为 MAAi 便捷线格式：4 字节大端长度 + UTF-8 JSON。

#include <nlohmann/json.hpp>

#include "MAAiAgent.h"

#include "MAOverlay.h"
#include "MAAScreenCapture.h"
#include "MAATouchInjector.h"
#include "core/version.h"

#include "core/ipc_client.h"
#include "core/ipc_message.h"
#include "../../include/MAAiAgent.h" // C ABI (MAAiAgentConfig)

#include <memory>
#include <string>

using maai::ipc::TcpClient;

static NSString* GetEnv(NSString* key, NSString* def) {
  NSString* v = [[NSProcessInfo processInfo] environment][key];
  return v && v.length ? v : def;
}

@interface MAAiAgent ()
@property(nonatomic, strong) NSString* serverHost;
@property(nonatomic, assign) uint16_t serverPort;
@property(nonatomic, strong) MAAScreenCapture* capture;
@property(nonatomic, strong) MAATouchInjector* injector;
@property(nonatomic, strong) MAOverlay* overlay;
@property(nonatomic, strong) NSTimer* streamTimer;
@property(nonatomic, assign) BOOL streamEnabled;
@end

@implementation MAAiAgent {
  std::unique_ptr<TcpClient> _client;
  dispatch_queue_t _workQueue;
  BOOL _started;
  BOOL _retryScheduled;
}

+ (instancetype)shared {
  static MAAiAgent* inst = nil;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ inst = [[MAAiAgent alloc] init]; });
  return inst;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _serverHost = @"127.0.0.1";
    _serverPort = MAAI_PORT;
    _screenshotFPS = 5;
    _jpegQuality = 70;
    _touchEnabled = YES;
    _overlayEnabled = YES;
    _streamEnabled = NO;
    _started = NO;
    _retryScheduled = NO;
    _workQueue = dispatch_queue_create("com.maai.agent", DISPATCH_QUEUE_SERIAL);
    _capture = [[MAAScreenCapture alloc] init];
    _capture.maxFPS = _screenshotFPS;
    _capture.jpegQuality = _jpegQuality;
    _injector = [[MAATouchInjector alloc] init];
    _injector.enabled = _touchEnabled;
    _overlay = [MAOverlay shared];
  }
  return self;
}

#pragma mark - 生命周期

- (BOOL)startWithHost:(NSString*)host port:(uint16_t)port {
  self.serverHost = host.length ? host : @"127.0.0.1";
  self.serverPort = port ?: MAAI_PORT;
  if (self.overlayEnabled) [self.overlay show];
  __weak MAAiAgent* ws = self;
  self.overlay.onSettingsTap = ^{ [ws showServerSettings]; };
  [self.overlay setConnected:NO host:self.serverHost];
  [self.overlay setAction:@"等待服务器..."];
  dispatch_async(_workQueue, ^{
    self->_started = YES;
    [self attemptConnect];
  });
  return YES;
}

- (void)stop {
  dispatch_async(_workQueue, ^{
    self->_started = NO;
    self->_retryScheduled = NO;
    if (self->_client) { self->_client->disconnect(); self->_client.reset(); }
  });
  dispatch_async(dispatch_get_main_queue(), ^{
    [self.streamTimer invalidate];
    self.streamTimer = nil;
  });
  [self.overlay setConnected:NO host:self.serverHost];
}

- (BOOL)connected {
  return _client ? _client->connected() : NO;
}

- (void)showServerSettings {
  [self.overlay presentServerSettingsWithHost:self.serverHost port:self.serverPort completion:^(NSString* h, uint16_t p) {
    NSUserDefaults* d = [NSUserDefaults standardUserDefaults];
    [d setObject:h forKey:@"MAAI_SERVER_HOST"];
    [d setInteger:p forKey:@"MAAI_SERVER_PORT"];
    [d synchronize];
    [self stop];
    [self startWithHost:h port:p];
  }];
}

- (void)setScreenshotFPS:(NSInteger)fps {
  _screenshotFPS = fps;
  _capture.maxFPS = fps;
  if (_streamEnabled) [self restartStreamTimer];
}

- (void)setJpegQuality:(NSInteger)q {
  _jpegQuality = q;
  _capture.jpegQuality = q;
}

#pragma mark - 连接循环

- (void)attemptConnect {
  if (!_started) return;  // stop 之后排队中的重连不再执行
  if (_client && _client->connected()) return;
  _client.reset(new TcpClient(std::string(self.serverHost.UTF8String ?: ""), self.serverPort));

  __weak MAAiAgent* wself = self;
  _client->setMessageHandler([wself](const nlohmann::json& msg) {
    MAAiAgent* s = wself;
    if (s) [s handleMessage:msg];
  });
  _client->setStateHandler([wself](bool connected) {
    MAAiAgent* s = wself;
    if (!s) return;
    dispatch_async(dispatch_get_main_queue(), ^{
      [s.overlay setConnected:connected host:s.serverHost];
    });
    if (connected) {
      [s sendStatus];
    } else {
      [s scheduleRetry];
    }
  });

  bool ok = _client->connect(5000);
  if (!ok && !_client->connected()) {
    [self.overlay setConnected:NO host:self.serverHost];
    [self scheduleRetry];
  }
}

- (void)scheduleRetry {
  dispatch_async(_workQueue, ^{
    if (self->_retryScheduled) return;
    self->_retryScheduled = YES;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3 * NSEC_PER_SEC)), self->_workQueue, ^{
      self->_retryScheduled = NO;
      [self attemptConnect];
    });
  });
}

#pragma mark - 消息处理

- (void)handleMessage:(const nlohmann::json&)msg {
  if (!msg.is_object()) return;
  std::string type = msg.value("type", "");
  std::string reqId = msg.value("req_id", "");
  std::string cmd = msg.value("cmd", "");
  nlohmann::json params = msg.value("params", nlohmann::json::object());

  if (type == "request") {
    [self handleCommand:[NSString stringWithUTF8String:cmd.c_str()] params:params
                reqId:[NSString stringWithUTF8String:reqId.c_str()]];
  } else if (type == "event") {
    // 服务器->agent 事件（目前无）
  }
}

- (void)respond:(NSString*)reqId ok:(BOOL)ok result:(nlohmann::json)result error:(NSString*)error {
  if (!_client || !_client->connected()) return;
  nlohmann::json r;
  r["v"] = maai::ipc::kProtocolVersion;
  r["type"] = "response";
  r["req_id"] = reqId ? reqId.UTF8String : "";
  r["ok"] = ok;
  r["result"] = result;
  r["error"] = error ? error.UTF8String : "";
  _client->send(r);
}

- (void)sendEvent:(NSString*)name payload:(nlohmann::json)payload {
  if (!_client || !_client->connected()) return;
  nlohmann::json e;
  e["v"] = maai::ipc::kProtocolVersion;
  e["type"] = "event";
  e["event"] = name ? name.UTF8String : "";
  e["payload"] = payload;
  _client->send(e);
}

- (void)handleCommand:(NSString*)cmd params:(const nlohmann::json&)p reqId:(NSString*)reqId {
  if ([cmd isEqualToString:@"PING"]) {
    [self respond:reqId ok:YES result:{{"pong", true}} error:nil];
    return;
  }
  if ([cmd isEqualToString:@"STATUS"]) {
    [self sendStatusReply:reqId];
    return;
  }
  if ([cmd isEqualToString:@"SCREENCAP"]) {
    [self handleScreencap:p reqId:reqId];
    return;
  }
  if ([cmd isEqualToString:@"CLICK"]) {
    BOOL ok = [_injector clickAtX:(int32_t)p.value("x", 0) y:(int32_t)p.value("y", 0)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"click failed"];
    return;
  }
  if ([cmd isEqualToString:@"SWIPE"]) {
    BOOL ok = [_injector swipeFromX:(int32_t)p.value("x1", 0) y1:(int32_t)p.value("y1", 0)
                               toX:(int32_t)p.value("x2", 0) y2:(int32_t)p.value("y2", 0)
                           duration:(int32_t)p.value("duration", 200)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"swipe failed"];
    return;
  }
  if ([cmd isEqualToString:@"TOUCH_DOWN"]) {
    BOOL ok = [_injector touchDownContact:(int32_t)p.value("contact", 0) x:(int32_t)p.value("x", 0) y:(int32_t)p.value("y", 0) pressure:(int32_t)p.value("pressure", 1)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"touch failed"];
    return;
  }
  if ([cmd isEqualToString:@"TOUCH_MOVE"]) {
    BOOL ok = [_injector touchMoveContact:(int32_t)p.value("contact", 0) x:(int32_t)p.value("x", 0) y:(int32_t)p.value("y", 0) pressure:(int32_t)p.value("pressure", 1)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"touch failed"];
    return;
  }
  if ([cmd isEqualToString:@"TOUCH_UP"]) {
    BOOL ok = [_injector touchUpContact:(int32_t)p.value("contact", 0)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"touch failed"];
    return;
  }
  if ([cmd isEqualToString:@"PRESS_KEY"]) {
    BOOL ok = [_injector pressKey:(int32_t)p.value("keycode", 0)];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"press key failed"];
    return;
  }
  if ([cmd isEqualToString:@"INPUT_TEXT"]) {
    std::string s = p.value("text", "");
    BOOL ok = [_injector inputText:[NSString stringWithUTF8String:s.c_str()]];
    [self respond:reqId ok:ok result:nlohmann::json() error:ok ? nil : @"input text failed"];
    return;
  }
  if ([cmd isEqualToString:@"DISPLAY"]) {
    std::string s = p.value("text", "");
    [self.overlay setAction:[NSString stringWithUTF8String:s.c_str()]];
    [self respond:reqId ok:YES result:nlohmann::json() error:nil];
    return;
  }
  if ([cmd isEqualToString:@"SET_STREAM"]) {
    bool on = p.value("enable", false);
    if (p.contains("fps")) _capture.maxFPS = (NSInteger)p.value("fps", 5);
    if (p.contains("quality")) _capture.jpegQuality = (NSInteger)p.value("quality", 70);
    _streamEnabled = on;
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.streamEnabled) [self startStreamTimer]; else [self stopStreamTimer];
    });
    [self respond:reqId ok:YES result:{{"stream", on}} error:nil];
    return;
  }
  if ([cmd isEqualToString:@"SET_TOUCH"]) {
    _injector.enabled = p.value("enable", true);
    _touchEnabled = _injector.enabled;
    [self respond:reqId ok:YES result:nlohmann::json() error:nil];
    return;
  }
  if ([cmd isEqualToString:@"SET_OVERLAY"]) {
    bool on = p.value("enable", true);
    dispatch_async(dispatch_get_main_queue(), ^{
      if (on) [self.overlay show]; else [self.overlay hide];
    });
    [self respond:reqId ok:YES result:nlohmann::json() error:nil];
    return;
  }
  [self respond:reqId ok:NO result:nlohmann::json() error:@"unknown command"];
}

- (void)handleScreencap:(const nlohmann::json&)p reqId:(NSString*)reqId {
  std::string format = p.value("format", "jpeg");
  if (format == "raw") {
    __block nlohmann::json result;
    __block BOOL done = NO;
    [_capture captureRawRGBA:^(const uint8_t* rgba, size_t width, size_t height) {
      NSData* raw = [NSData dataWithBytes:rgba length:width * height * 4];
      result = {
        {"format", "raw"},
        {"width", width},
        {"height", height},
        {"data", [[raw base64EncodedStringWithOptions:0] UTF8String]}
      };
      done = YES;
    }];
    if (done) [self respond:reqId ok:YES result:result error:nil];
    else [self respond:reqId ok:NO result:nlohmann::json() error:@"capture failed"];
    return;
  }
  NSData* jpeg = [_capture captureJPEG];
  if (!jpeg) { [self respond:reqId ok:NO result:nlohmann::json() error:@"capture failed"]; return; }
  nlohmann::json result = {{"format", "jpeg"}, {"data", [[jpeg base64EncodedStringWithOptions:0] UTF8String]}};
  [self respond:reqId ok:YES result:result error:nil];
}

- (void)sendStatus {
  [self sendEvent:@"STATUS" payload:[self statusPayload]];
}

- (void)sendStatusReply:(NSString*)reqId {
  [self respond:reqId ok:YES result:[self statusPayload] error:nil];
}

- (nlohmann::json)statusPayload {
  CGSize px = _capture.currentPixelSize;
  nlohmann::json j = {
    {"agent", "MAAiAgent"},
    {"version", MAAI_VERSION},
    {"protocol", maai::ipc::kProtocolVersion},
    {"connected", _client ? _client->connected() : false},
    {"screen", {{"width", (int)px.width}, {"height", (int)px.height}}},
    {"fps", (int)_screenshotFPS},
    {"touch_enabled", _touchEnabled},
    {"overlay_enabled", _overlayEnabled}
  };
  return j;
}

#pragma mark - 截图流

- (void)startStreamTimer {
  dispatch_async(dispatch_get_main_queue(), ^{
    [self.streamTimer invalidate];
    NSInteger fps = MAX(1, MIN(20, _capture.maxFPS));
    self.streamTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 / fps
                                                        target:self
                                                      selector:@selector(streamTick)
                                                      userInfo:nil
                                                       repeats:YES];
  });
}

- (void)stopStreamTimer {
  dispatch_async(dispatch_get_main_queue(), ^{
    [self.streamTimer invalidate];
    self.streamTimer = nil;
  });
}

- (void)restartStreamTimer {
  if (_streamEnabled) {
    [self stopStreamTimer];
    [self startStreamTimer];
  }
}

- (void)streamTick {
  if (!_client || !_client->connected()) return;
  NSData* jpeg = [_capture captureJPEG];
  if (!jpeg) return;
  nlohmann::json payload = {{"format", "jpeg"}, {"data", [[jpeg base64EncodedStringWithOptions:0] UTF8String]}};
  [self sendEvent:@"SCREENSHOT" payload:payload];
}

#pragma mark - C ABI

+ (void)maybeAutoStart {
  NSString* host = GetEnv(@"MAAI_SERVER_HOST", nil);
  uint16_t port = MAAI_PORT;
  if (host) {
    port = (uint16_t)[GetEnv(@"MAAI_SERVER_PORT", @"17171") intValue];
  } else {
    // 游戏内保存过的服务器地址（浮层“点击设置”）
    NSUserDefaults* d = [NSUserDefaults standardUserDefaults];
    NSString* dh = [d stringForKey:@"MAAI_SERVER_HOST"];
    if (dh.length) {
      host = dh;
      port = (uint16_t)[d integerForKey:@"MAAI_SERVER_PORT"];
    }
  }

  MAAiAgent* agent = [MAAiAgent shared];
  if (!host.length) {
    // 第一次使用：还没配置服务器。仍然显示浮窗，让用户点浮窗标签设置地址。
    dispatch_async(dispatch_get_main_queue(), ^{
      if (agent.overlayEnabled) [agent.overlay show];
      __weak MAAiAgent* wa = agent;
      agent.overlay.onSettingsTap = ^{ [wa showServerSettings]; };
      [agent.overlay setConnected:NO host:@"未配置"];
      [agent.overlay setAction:@"点击设置服务器"];
    });
    return;
  }
  if (port == 0) port = MAAI_PORT;
  [agent startWithHost:host port:port];
}

static void AppLoader(void) __attribute__((constructor));
static void AppLoader(void) {
  @autoreleasepool {
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
      [MAAiAgent maybeAutoStart];
    });
  }
}

@end

#pragma mark - C ABI 实现

extern "C" {

const char* MAAiAgentVersion(void) { return MAAI_VERSION; }

int MAAiAgentStart(const MAAiAgentConfig* config) {
  NSString* host = @"127.0.0.1";
  uint16_t port = MAAI_PORT;
  if (config && config->server_host && config->server_host[0]) host = [NSString stringWithUTF8String:config->server_host];
  if (config && config->server_port) port = config->server_port;
  MAAiAgent* agent = [MAAiAgent shared];
  if (config) {
    NSUserDefaults* d = [NSUserDefaults standardUserDefaults];
    [d setObject:host forKey:@"MAAI_SERVER_HOST"];
    [d setInteger:port forKey:@"MAAI_SERVER_PORT"];
    [d synchronize];
    if (config->screenshot_fps > 0) agent.screenshotFPS = config->screenshot_fps;
    if (config->jpeg_quality > 0) agent.jpegQuality = config->jpeg_quality;
    if (config->touch_enabled >= 0) agent.touchEnabled = config->touch_enabled != 0;
    if (config->overlay_enabled >= 0) agent.overlayEnabled = config->overlay_enabled != 0;
  }
  return [agent startWithHost:host port:port] ? 1 : 0;
}

int MAAiAgentStop(void) {
  [[MAAiAgent shared] stop];
  return 1;
}

int MAAiAgentIsRunning(void) {
  return [[MAAiAgent shared] connected] ? 1 : 0;
}

}
