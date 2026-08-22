#pragma once

#import <UIKit/UIKit.h>

// 触摸注入。
//
// 说明: iOS 无公开的触摸合成 API，这里使用经典的
// IOHIDEvent -> UIApplication _handleHIDEvent: 私有路线。
// 仅用于个人学习/自动化研究；在 LiveContainer 等受限沙盒环境可能失败，
// 失败时对应方法返回 NO 并记日志，自动化会拿到失败动作后重试。
@interface MAATouchInjector : NSObject

@property(nonatomic, assign) BOOL enabled;

// 注意: 坐标单位与 MaaFramework 一致（像素），内部换算成点。
- (BOOL)clickAtX:(int32_t)x y:(int32_t)y;
- (BOOL)swipeFromX:(int32_t)x1 y1:(int32_t)y1 toX:(int32_t)x2 y2:(int32_t)y2 duration:(int32_t)durationMs;
- (BOOL)touchDownContact:(int32_t)contact x:(int32_t)x y:(int32_t)y pressure:(int32_t)pressure;
- (BOOL)touchMoveContact:(int32_t)contact x:(int32_t)x y:(int32_t)y pressure:(int32_t)pressure;
- (BOOL)touchUpContact:(int32_t)contact;
- (BOOL)pressKey:(int32_t)keycode;
- (BOOL)inputText:(NSString*)text;

@end
