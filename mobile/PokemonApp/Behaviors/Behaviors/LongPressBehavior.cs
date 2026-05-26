namespace PokemonApp.Behaviors;

/// <summary>
/// 为任意 View 添加长按手势支持。
/// Android：使用原生 SetOnLongClickListener。
/// 其他平台：使用 PointerGestureRecognizer + 计时器模拟。
/// 用法（XAML）：
///   <Border ...>
///     <Border.Behaviors>
///       <behaviors:LongPressBehavior LongPressed="OnHandler" CommandParameter="{Binding .}" />
///     </Border.Behaviors>
///   </Border>
/// </summary>
public class LongPressBehavior : Behavior<View>
{
    private View? _attachedView;

    /// <summary>
    /// 传递给事件处理器的参数
    /// </summary>
    public object? CommandParameter
    {
        get => GetValue(CommandParameterProperty);
        set => SetValue(CommandParameterProperty, value);
    }

    public static readonly BindableProperty CommandParameterProperty =
        BindableProperty.Create(nameof(CommandParameter), typeof(object), typeof(LongPressBehavior));

    /// <summary>
    /// 长按事件
    /// </summary>
    public event EventHandler<object?>? LongPressed;

    protected override void OnAttachedTo(View bindable)
    {
        base.OnAttachedTo(bindable);
        _attachedView = bindable;
        bindable.HandlerChanged += OnHandlerChanged;
    }

    protected override void OnDetachingFrom(View bindable)
    {
        bindable.HandlerChanged -= OnHandlerChanged;
        DetachNative(bindable);
        _attachedView = null;
        base.OnDetachingFrom(bindable);
    }

    private void OnHandlerChanged(object? sender, EventArgs e)
    {
        if (_attachedView?.Handler != null)
            AttachNative(_attachedView);
    }

    private void FireLongPress()
    {
        LongPressed?.Invoke(this, CommandParameter);
    }

#if ANDROID
    private void AttachNative(View view)
    {
        if (view.Handler?.PlatformView is Android.Views.View nativeView)
        {
            nativeView.LongClickable = true;
            nativeView.LongClick += OnAndroidLongClick;
        }
    }

    private void DetachNative(View view)
    {
        if (view.Handler?.PlatformView is Android.Views.View nativeView)
        {
            nativeView.LongClick -= OnAndroidLongClick;
        }
    }

    private void OnAndroidLongClick(object? sender, Android.Views.View.LongClickEventArgs e)
    {
        e.Handled = true;
        FireLongPress();
    }
#else
    // 非 Android 平台：用 PointerGestureRecognizer 模拟长按
    private CancellationTokenSource? _cts;
    private bool _isPressed;

    private void AttachNative(View view)
    {
        var recognizer = new PointerGestureRecognizer();
        recognizer.PointerPressed += (s, e) =>
        {
            _isPressed = true;
            _cts?.Cancel();
            _cts = new CancellationTokenSource();
            var token = _cts.Token;
            Task.Delay(500, token).ContinueWith(t =>
            {
                if (!t.IsCanceled && _isPressed)
                    MainThread.BeginInvokeOnMainThread(FireLongPress);
            });
        };
        recognizer.PointerReleased += (s, e) => { _isPressed = false; _cts?.Cancel(); };
        recognizer.PointerExited += (s, e) => { _isPressed = false; _cts?.Cancel(); };
        view.GestureRecognizers.Add(recognizer);
    }

    private void DetachNative(View view)
    {
        _cts?.Cancel();
    }
#endif
}
