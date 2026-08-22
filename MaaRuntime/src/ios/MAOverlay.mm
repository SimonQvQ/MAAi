#include "MAOverlay.h"

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
  UIWindow* w = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
  w.windowLevel = UIWindowLevelAlert + 1;
  w.hidden = NO;
  w.userInteractionEnabled = NO; // 不拦截游戏触摸
  w.rootViewController = [UIViewController new];
  w.backgroundColor = [UIColor clearColor];

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

  _actionLabel = [[UILabel alloc] initWithFrame:CGRectMake(x, y + 27, labelW, 22)];
  _actionLabel.font = [UIFont systemFontOfSize:12];
  _actionLabel.textColor = [UIColor colorWithWhite:1 alpha:0.95];
  _actionLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.4];
  _actionLabel.textAlignment = NSTextAlignmentCenter;
  _actionLabel.layer.cornerRadius = 8;
  _actionLabel.clipsToBounds = YES;

  [w addSubview:_statusLabel];
  [w addSubview:_actionLabel];
  return w;
}

- (void)show {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!_window) { _window = [self buildWindow]; }
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
    _statusLabel.text = [NSString stringWithFormat:@"MAAi %@  %@", dot, _lastHost];
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

@end
