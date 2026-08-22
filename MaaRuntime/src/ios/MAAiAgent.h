#pragma once

#import <Foundation/Foundation.h>

// MAAiAgent: 注入明日方舟进程的“眼睛/手/表情包”。
// 主动拨号连接 Docker 里的 maai-server（MaaFramework + MXU），
// 通道复用 MAAi 线格式：4 字节大端长度 + JSON。
@interface MAAiAgent : NSObject

+ (instancetype)shared;

// 开始连接服务器；失败会自动重试（每 5s）。
- (BOOL)startWithHost:(NSString*)host port:(uint16_t)port;
- (void)stop;

@property(nonatomic, readonly) BOOL connected;
@property(nonatomic, assign) NSInteger screenshotFPS;   // 流推送频率，默认 5
@property(nonatomic, assign) NSInteger jpegQuality;     // 0~100，默认 70
@property(nonatomic, assign) BOOL touchEnabled;
@property(nonatomic, assign) BOOL overlayEnabled;

@end
