#import "MAAScreenCapture.h"

#import <CoreGraphics/CoreGraphics.h>

@implementation MAAScreenCapture

- (instancetype)init {
  self = [super init];
  if (self) {
    _maxFPS = 5;
    _jpegQuality = 70;
  }
  return self;
}

- (UIWindow*)keyWindow {
  if (@available(iOS 13.0, *)) {
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
      if (![scene isKindOfClass:UIWindowScene.class]) continue;
      UIWindowScene* ws = (UIWindowScene*)scene;
      if (ws.activationState != UISceneActivationStateForegroundActive &&
          ws.activationState != UISceneActivationStateForegroundInactive) continue;
      for (UIWindow* w in ws.windows) {
        if (w.isKeyWindow) return w;
      }
      return ws.windows.firstObject;
    }
  }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  return UIApplication.sharedApplication.windows.firstObject;
#pragma clang diagnostic pop
}

- (void)runOnMainSynchronous:(void (NS_NOESCAPE ^)(void))block {
  if ([NSThread isMainThread]) {
    block();
  } else {
    dispatch_sync(dispatch_get_main_queue(), block);
  }
}

- (UIImage*)captureImage {
  __block UIImage* result = nil;
  [self runOnMainSynchronous:^{
    UIWindow* window = [self keyWindow];
    if (!window) return;
    CGRect bounds = window.bounds;
    if (bounds.size.width < 1 || bounds.size.height < 1) return;
    CGFloat scale = window.screen ? window.screen.scale : UIScreen.mainScreen.scale;
    if (@available(iOS 10.0, *)) {
      UIGraphicsImageRendererFormat* fmt = [UIGraphicsImageRendererFormat preferredFormat];
      fmt.scale = scale;
      fmt.opaque = YES;
      UIGraphicsImageRenderer* renderer =
          [[UIGraphicsImageRenderer alloc] initWithSize:bounds.size format:fmt];
      result = [renderer imageWithActions:^(UIGraphicsImageRendererContext* ctx) {
        [window drawViewHierarchyInRect:bounds afterScreenUpdates:NO];
      }];
    } else {
      UIGraphicsBeginImageContextWithOptions(bounds.size, YES, scale);
      [window drawViewHierarchyInRect:bounds afterScreenUpdates:NO];
      result = UIGraphicsGetImageFromCurrentImageContext();
      UIGraphicsEndImageContext();
    }
  }];
  return result;
}

- (NSData*)captureJPEG {
  UIImage* img = [self captureImage];
  if (!img) return nil;
  NSInteger q = MIN(100, MAX(1, _jpegQuality));
  return UIImageJPEGRepresentation(img, (CGFloat)q / 100.0);
}

- (void)captureRawRGBA:(void (^)(const uint8_t*, size_t, size_t))completion {
  UIImage* img = [self captureImage];
  if (!img) {
    completion(nil, 0, 0);
    return;
  }
  CGImageRef cg = img.CGImage;
  if (!cg) {
    completion(nil, 0, 0);
    return;
  }
  size_t w = CGImageGetWidth(cg);
  size_t h = CGImageGetHeight(cg);
  if (w == 0 || h == 0) {
    completion(nil, 0, 0);
    return;
  }
  uint8_t* buf = (uint8_t*)calloc(w * h * 4, 1);
  CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
  CGContextRef ctx = CGBitmapContextCreate(buf, w, h, 8, w * 4, cs,
                                           kCGImageAlphaPremultipliedLast |
                                               kCGBitmapByteOrder32Big);
  if (ctx) {
    CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), cg);
    CGContextRelease(ctx);
  }
  CGColorSpaceRelease(cs);
  completion(buf, w, h);
  free(buf);
}

- (CGSize)currentPixelSize {
  __block CGSize size = CGSizeZero;
  [self runOnMainSynchronous:^{
    UIWindow* w = [self keyWindow];
    CGFloat scale = w.screen ? w.screen.scale : UIScreen.mainScreen.scale;
    size = CGSizeMake(w.bounds.size.width * scale, w.bounds.size.height * scale);
  }];
  return size;
}

@end
