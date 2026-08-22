#pragma once

#import <UIKit/UIKit.h>

// 进程内截图：把当前 UIWindow(游戏画面) 画成 UIImage。
// 因为截图涉及 UIKit，所有操作都必须在主线程执行（类内部自动切换）。
@interface MAAScreenCapture : NSObject

@property(nonatomic, assign) NSInteger maxFPS;       // 仅影响流推送频率（由外部控制），默认 5
@property(nonatomic, assign) NSInteger jpegQuality;  // 0~100

// 拿到 JPEG 数据（用于 App 预览 IPC 传输）。
- (nullable NSData*)captureJPEG;

// 拿到 RGBA8888 原始像素（用于 MaaFramework MaaImageBuffer）。
// 回调在调用线程同步返回（内部若不在主线程会 dispatch_sync 切换）。
- (void)captureRawRGBA:(void (^)(const uint8_t* rgba, size_t width, size_t height))completion;

// 屏幕物理像素尺寸（截图回调前调用无效）。
- (CGSize)currentPixelSize;

@end
