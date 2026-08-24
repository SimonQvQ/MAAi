#include "MAOverlay.h"

// 点击穿透窗口：只有点中状态栏/操作栏才响应，其余触摸交给游戏。
@interface MAOverlayWindow : UIWindow
@property(nonatomic, strong) NSArray<UIView*>* tappableViews;
@end

@implementation MAOverlayWindow
- (UIView*)hitTest:(CGPoint)point withEvent:(UIEvent*)event {
  // 弹设置对话框时，整个窗口正常响应（包括输入框/键盘）
  if (self.rootViewController.presentedViewController) {
    return [super hitTest:point withEvent:event];
  }
  UIView* v = [super hitTest:point withEvent:event];
  if (!v) return nil;
  for (UIView* t in _tappableViews) {
    if ([v isDescendantOfView:t]) return v;
  }
  return nil; // 其余区域穿透给游戏
}
@end

@interface MAOverlay ()
@property(nonatomic, strong) UIWindow* window;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UILabel* actionLabel;
@property(nonatomic, strong) NSString* lastHost;
@end

@implementation MAOverlay

+ (instancetype)shared {
  static MAOverlay* inst = nil;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ inst = [[MAOverlay alloc] init]; });
  return inst;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _lastHost = @"";
  }
  return self;
}

- (UIWindow*)buildWindow {
  MAOverlayWindow* w = [[MAOverlayWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
  w.windowLevel = UIWindowLevelAlert + 1;
  w.hidden = NO;
  w.userInteractionEnabled = YES;
  w.rootViewController = [UIViewController new];
  w.backgroundColor = [UIColor clearColor];
  [self attachScene:w];

  CGFloat y = 34; // 避开状态栏
  CGFloat wd = [UIScreen mainScreen].bounds.size.width - 24;
  CGFloat labelW = MIN(wd, 520);
  CGFloat x = ([UIScreen mainScreen].bounds.size.width - labelW) / 2;

  _statusLabel = [[UILabel alloc] initWithFrame:CGRectMake(x, y, labelW, 24)];
  _statusLabel.font = [UIFont boldSystemFontOfSize:12];
  _statusLabel.textColor = [UIColor whiteColor];
  _statusLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
  _statusLabel.textAlignment = NSTextAlignmentCenter;
  _statusLabel.layer.cornerRadius = 8;
  _statusLabel.clipsToBounds = YES;
  _statusLabel.userInteractionEnabled = YES;
  [_statusLabel addGestureRecognizer:[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(settingsTapped)]];

  _actionLabel = [[UILabel alloc] initWithFrame:CGRectMake(x, y + 27, labelW, 22)];
  _actionLabel.font = [UIFont systemFontOfSize:12];
  _actionLabel.textColor = [UIColor colorWithWhite:1 alpha:0.95];
  _actionLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.4];
  _actionLabel.textAlignment = NSTextAlignmentCenter;
  _actionLabel.layer.cornerRadius = 8;
  _actionLabel.clipsToBounds = YES;

  [w.rootViewController.view addSubview:_statusLabel];
  [w.rootViewController.view addSubview:_actionLabel];
  w.tappableViews = @[ _statusLabel, _actionLabel ];
  return w;
}

// iOS 13+ 多场景：不绑 scene 的 UIWindow 不会合成显示。
- (void)attachScene:(UIWindow*)w {
  if (@available(iOS 13.0, *)) {
    for (UIScene* sc in [UIApplication sharedApplication].connectedScenes) {
      if ([sc isKindOfClass:[UIWindowScene class]] && sc.activationState != UISceneActivationStateUnattached) {
        w.windowScene = (UIWindowScene*)sc;
        break;
      }
    }
  }
}

- (void)settingsTapped {
  if (_onSettingsTap) _onSettingsTap();
}

- (void)show {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!_window) { _window = [self buildWindow]; }
    [self attachScene:_window]; // scene 可能晚于窗口创建才连接
    _window.hidden = NO;
  });
}

- (void)hide {
  dispatch_async(dispatch_get_main_queue(), ^{ _window.hidden = YES; });
}

- (void)setConnected:(BOOL)connected host:(NSString*)host {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (host) _lastHost = [host copy];
    NSString* dot = connected ? @"● 已连接" : @"○ 未连接";
    _statusLabel.text = [NSString stringWithFormat:@"MAAi %@  %@ · 点击设置", dot, _lastHost];
  });
}

- (void)setAction:(NSString*)action {
  dispatch_async(dispatch_get_main_queue(), ^{
    _actionLabel.text = action && action.length ? action : @"就绪";
  });
}

- (void)setLog:(NSString*)text {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (text.length) _statusLabel.text = text;
  });
}

- (void)presentServerSettingsWithHost:(NSString*)host port:(uint16_t)port completion:(void (^)(NSString*, uint16_t))completion {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!_window) { _window = [self buildWindow]; }
    [self attachScene:_window];
    _window.hidden = NO;
    UIAlertController* ac = [UIAlertController alertControllerWithTitle:@"MAAi 服务器"
                                                               message:@"填写 Docker 服务器地址（IP 或域名）"
                                                        preferredStyle:UIAlertControllerStyleAlert];
    [ac addTextFieldWithConfigurationHandler:^(UITextField* tf) {
      tf.text = host;
      tf.placeholder = @"例如 192.168.1.10";
      tf.keyboardType = UIKeyboardTypeURL;
      tf.autocapitalizationType = UITextAutocapitalizationTypeNone;
      tf.autocorrectionType = UITextAutocorrectionTypeNo;
    }];
    [ac addTextFieldWithConfigurationHandler:^(UITextField* tf) {
      tf.text = [NSString stringWithFormat:@"%u", port];
      tf.placeholder = @"端口";
      tf.keyboardType = UIKeyboardTypeNumberPad;
    }];
    [ac addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [ac addAction:[UIAlertAction actionWithTitle:@"保存并连接" style:UIAlertActionStyleDefault handler:^(UIAlertAction* a) {
      NSString* h = ac.textFields[0].text;
      NSString* p = ac.textFields[1].text;
      NSString* host2 = (h && h.length) ? h : @"127.0.0.1";
      uint16_t port2 = (uint16_t)[p intValue];
      if (port2 == 0) port2 = 17171;
      if (completion) completion(host2, port2);
    }]];
    [_window.rootViewController presentViewController:ac animated:YES completion:nil];
  });
}

@end
