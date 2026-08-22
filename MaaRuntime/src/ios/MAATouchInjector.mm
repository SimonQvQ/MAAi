#import "MAATouchInjector.h"

#include <cmath>
#include <mach/mach_time.h>

#include "core/log.h"

// ---- 私有 API 声明 ----
#if !defined(__IOHIDEvent_h__)
typedef unsigned int IOOptionBits;
typedef struct __IOHIDEvent* IOHIDEventRef;
typedef double IOHIDFloat;
enum {
  kIOHIDDigitizerTransducerTypeHand = 4,
  kIOHIDDigitizerTransducerTypeFinger = 5,
};
enum {
  kIOHIDDigitizerEventRange    = 0x00000001,
  kIOHIDDigitizerEventTouch    = 0x00000002,
  kIOHIDDigitizerEventPosition = 0x00000004,
};
extern "C" {
IOHIDEventRef IOHIDEventCreateDigitizerEvent(
    CFAllocatorRef allocator, uint64_t timeStamp,
    uint32_t type, uint32_t index, uint32_t identity, uint32_t eventMask,
    uint32_t buttonMask, IOHIDFloat x, IOHIDFloat y, IOHIDFloat z,
    IOHIDFloat tipPressure, IOHIDFloat barrelPressure, Boolean range,
    Boolean touch, IOOptionBits options);
IOHIDEventRef IOHIDEventCreateDigitizerFingerEvent(
    CFAllocatorRef allocator, uint64_t timeStamp,
    uint32_t index, uint32_t identity, uint32_t eventMask,
    IOHIDFloat x, IOHIDFloat y, IOHIDFloat z, IOHIDFloat tipPressure,
    IOHIDFloat twist, Boolean range, Boolean touch, IOOptionBits options);
}
#endif

@implementation MAATouchInjector {
  NSMutableDictionary<NSNumber*, NSValue*>* _downTouches;  // contact -> CGPoint(点坐标)
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _enabled = YES;
    _downTouches = [NSMutableDictionary new];
  }
  return self;
}

- (BOOL)sendHIDEvent:(IOHIDEventRef)event {
  if (!_enabled || !event) return NO;
  UIApplication* app = UIApplication.sharedApplication;
  SEL sel = NSSelectorFromString(@"_handleHIDEvent:");
  if (![app respondsToSelector:sel]) {
    maai::Log::warn("UIApplication does not respond to _handleHIDEvent:, touch injection unavailable");
    return NO;
  }
  [app performSelector:sel withObject:(__bridge id)event];
  return YES;
}

- (CGFloat)screenScale {
  return UIScreen.mainScreen.scale;
}

- (CGPoint)pointsFromPixelsX:(int32_t)x y:(int32_t)y {
  CGFloat s = [self screenScale];
  if (s < 1) s = 1;
  return CGPointMake(x / s, y / s);
}

- (BOOL)touchDownContact:(int32_t)contact x:(int32_t)x y:(int32_t)y pressure:(int32_t)pressure {
  uint64_t ts = mach_absolute_time();
  CGPoint pt = [self pointsFromPixelsX:x y:y];
  IOHIDEventRef ev = IOHIDEventCreateDigitizerFingerEvent(
      kCFAllocatorDefault, ts, (uint32_t)contact, (uint32_t)contact + 9000,
      kIOHIDDigitizerEventRange | kIOHIDDigitizerEventTouch | kIOHIDDigitizerEventPosition,
      pt.x, pt.y, 0, pressure > 0 ? 1.0 : 0.0, 0, true, true, 0);
  BOOL ok = [self sendHIDEvent:ev];
  if (ev) CFRelease(ev);
  if (ok) _downTouches[@(contact)] = [NSValue valueWithCGPoint:pt];
  return ok;
}

- (BOOL)touchMoveContact:(int32_t)contact x:(int32_t)x y:(int32_t)y pressure:(int32_t)pressure {
  uint64_t ts = mach_absolute_time();
  CGPoint pt = [self pointsFromPixelsX:x y:y];
  IOHIDEventRef ev = IOHIDEventCreateDigitizerFingerEvent(
      kCFAllocatorDefault, ts, (uint32_t)contact, (uint32_t)contact + 9000,
      kIOHIDDigitizerEventPosition,
      pt.x, pt.y, 0, pressure > 0 ? 1.0 : 0.0, 0, true, true, 0);
  BOOL ok = [self sendHIDEvent:ev];
  if (ev) CFRelease(ev);
  if (ok) _downTouches[@(contact)] = [NSValue valueWithCGPoint:pt];
  return ok;
}

- (BOOL)touchUpContact:(int32_t)contact {
  uint64_t ts = mach_absolute_time();
  CGPoint pt = CGPointZero;
  NSValue* v = _downTouches[@(contact)];
  if (v) pt = v.CGPointValue;
  IOHIDEventRef ev = IOHIDEventCreateDigitizerFingerEvent(
      kCFAllocatorDefault, ts, (uint32_t)contact, (uint32_t)contact + 9000,
      kIOHIDDigitizerEventRange | kIOHIDDigitizerEventTouch,
      pt.x, pt.y, 0, 0, 0, false, false, 0);
  BOOL ok = [self sendHIDEvent:ev];
  if (ev) CFRelease(ev);
  [_downTouches removeObjectForKey:@(contact)];
  return ok;
}

- (BOOL)clickAtX:(int32_t)x y:(int32_t)y {
  maai::Log::debug("tap " + std::to_string(x) + "," + std::to_string(y));
  [self touchDownContact:1 x:x y:y pressure:1];
  [NSThread sleepForTimeInterval:0.02];
  return [self touchUpContact:1];
}

- (BOOL)swipeFromX:(int32_t)x1 y1:(int32_t)y1 toX:(int32_t)x2 y2:(int32_t)y2 duration:(int32_t)durationMs {
  if (durationMs < 16) durationMs = 16;
  [self touchDownContact:1 x:x1 y:y1 pressure:1];
  int steps = MAX(2, (int)(durationMs / 16));
  for (int i = 1; i <= steps; i++) {
    float t = (float)i / (float)steps;
    int32_t cx = (int32_t)lroundf((float)x1 + (t * (float)(x2 - x1)));
    int32_t cy = (int32_t)lroundf((float)y1 + (t * (float)(y2 - y1)));
    [self touchMoveContact:1 x:cx y:cy pressure:1];
    [NSThread sleepForTimeInterval:0.016];
  }
  return [self touchUpContact:1];
}

- (BOOL)pressKey:(int32_t)keycode {
  (void)keycode;
  maai::Log::warn("pressKey is not supported on iOS, ignored");
  return NO;
}

- (BOOL)inputText:(NSString*)text {
  (void)text;
  maai::Log::warn("inputText is not supported on iOS without accessibility hook, ignored");
  return NO;
}

@end
