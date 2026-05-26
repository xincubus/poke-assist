using PokemonApp.Models;
using PokemonApp.ViewModels;

namespace PokemonApp.Views;

public partial class ChatPage : ContentPage
{
    private readonly ChatViewModel _vm;

    public ChatPage(ChatViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;

        // 新消息时自动滚动到底部
        _vm.Messages.CollectionChanged += (s, e) =>
        {
            if (_vm.Messages.Count > 0)
            {
                MainThread.BeginInvokeOnMainThread(async () =>
                {
                    await Task.Delay(50);
                    MessageList.ScrollTo(_vm.Messages.Count - 1, position: ScrollToPosition.End, animate: true);
                });
            }
        };

        // 发送时收起键盘：监听 IsBusy 变为 true（Command 执行完毕后），延迟隐藏防止 Entry 抢焦点
        _vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(_vm.IsBusy) && _vm.IsBusy)
                MainThread.BeginInvokeOnMainThread(async () =>
                {
                    await Task.Delay(100);
                    HideKeyboard();
                });
        };
    }

    /// <summary>
    /// 长按消息气泡弹出操作菜单：复制全文 / 选择文本
    /// </summary>
    private async void OnMessageLongPressed(object? sender, object? parameter)
    {
        if (parameter is not ChatMessage msg) return;

        // 如果已处于选择模式，不再弹菜单
        if (msg.IsSelectable) return;

        var action = await DisplayActionSheet("消息操作", "取消", null, "复制全文", "选择文本");

        switch (action)
        {
            case "复制全文":
                // 复制纯文本（去掉 markdown 链接语法）
                await Clipboard.Default.SetTextAsync(msg.PlainText);
                // 轻量提示
#if ANDROID
                Android.Widget.Toast.MakeText(Platform.CurrentActivity, "已复制", Android.Widget.ToastLength.Short)?.Show();
#endif
                break;

            case "选择文本":
                // 先退出其他消息的选择模式
                foreach (var m in _vm.Messages)
                {
                    if (m != msg && m.IsSelectable)
                        m.IsSelectable = false;
                }
                msg.IsSelectable = true;
                break;
        }
    }

    /// <summary>
    /// 退出选择文本模式
    /// </summary>
    private void OnExitSelectMode(object? sender, TappedEventArgs e)
    {
        if (e.Parameter is ChatMessage msg)
            msg.IsSelectable = false;
    }

    /// <summary>
    /// MarkdownLabel 内联链接被点击，在 app 内 WebView 打开计算器
    /// </summary>
    private async void OnMarkdownLinkClicked(object? sender, string url)
    {
        if (string.IsNullOrEmpty(url)) return;
        await Shell.Current.GoToAsync($"damagecalc?url={Uri.EscapeDataString(url)}");
    }

    private void HideKeyboard()
    {
        MessageEntry.Unfocus();
#if ANDROID
        if (Platform.CurrentActivity?.CurrentFocus != null)
        {
            var imm = (Android.Views.InputMethods.InputMethodManager?)
                Platform.CurrentActivity.GetSystemService(Android.Content.Context.InputMethodService);
            imm?.HideSoftInputFromWindow(Platform.CurrentActivity.CurrentFocus.WindowToken, 0);
        }
#endif
    }
}
