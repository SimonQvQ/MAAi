#pragma once

#import <UIKit/UIKit.h>

// 游戏内小浮层：顶部一条半透明标签，显示连接状态 + 当前操作文本。
// 所以 UI 操作都在主线程执行。
@interface MAOverlay : NSObject

+ (instancetype)shared;
- (void)show;
- (void)hide;
- (void)setConnected:(BOOL)connected host:(NSString*)host;
- (void)setAction:(NSString*)action;   // 当前操作（由服务器 DISPLAY 命令推送）
- (void)setLog:(NSString*)text;        // 调试日志（可选）

@end
