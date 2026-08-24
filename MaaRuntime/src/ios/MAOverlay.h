#pragma once

#import <UIKit/UIKit.h>

// 游戏内小浮层：顶部一条半透明标签，显示连接状态 + 当前操作文本，
// 以及一个"连接并开始/停止任务"按钮。
// 点击状态栏可弹出“服务器设置”对话框。所有 UI 操作都在主线程执行。
@interface MAOverlay : NSObject

+ (instancetype)shared;
- (void)show;
- (void)hide;
- (void)setConnected:(BOOL)connected host:(NSString*)host;
- (void)setAction:(NSString*)action;   // 当前操作（由服务器 DISPLAY 命令推送）
- (void)setLog:(NSString*)text;        // 调试日志（可选）
- (void)setTaskActive:(BOOL)active;    // 任务是否执行中（影响按钮文案）

// 点击浮层设置回调（由 MAAiAgent 注入）
@property(nonatomic, copy) void (^onSettingsTap)(void);
// 点击"连接并开始/停止"按钮回调（由 MAAiAgent 注入）
@property(nonatomic, copy) void (^onStartTap)(void);
// 弹出服务器设置对话框，保存后回调
- (void)presentServerSettingsWithHost:(NSString*)host
                                 port:(uint16_t)port
                           completion:(void (^)(NSString* host, uint16_t port))completion;

@end
