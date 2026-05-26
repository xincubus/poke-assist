using System.Collections.ObjectModel;
using PokemonApp.Services;
using PokemonApp.ViewModels;
using PokemonApp.Views;

namespace PokemonApp;

public partial class AppShell : Shell
{
	private readonly ChatHistoryService _historyService;
	private readonly ChatViewModel _chatViewModel;

	// 长按计时
	private CancellationTokenSource? _longPressCts;
	private const int LongPressMs = 500;

	public ObservableCollection<MenuItem> MenuItems { get; set; }
	public ObservableCollection<ChatHistoryItem> ChatHistories { get; set; }

	public AppShell(ChatHistoryService historyService, ChatViewModel chatViewModel)
	{
		InitializeComponent();

		_historyService = historyService;
		_chatViewModel = chatViewModel;

		// 初始化菜单项
		MenuItems = new ObservableCollection<MenuItem>
		{
			new MenuItem { Title = "对话", Route = "chat" },
			new MenuItem { Title = "宝可梦", Route = "pokemon" },
			new MenuItem { Title = "队伍", Route = "teams" },
			new MenuItem { Title = "使用率", Route = "home" },
			new MenuItem { Title = "伤害计算器", Route = "damagecalctab" },
			new MenuItem { Title = "设置", Route = "settings" }
		};

		// 初始化历史对话
		ChatHistories = new ObservableCollection<ChatHistoryItem>();

		BindingContext = this;
		Loaded += OnShellLoaded;

		// 注册子页面路由
		Routing.RegisterRoute("addpokemon", typeof(AddPokemonPage));
		Routing.RegisterRoute("addteam", typeof(AddTeamPage));
		Routing.RegisterRoute("damagecalc", typeof(DamageCalcPage));
	}

	private async void OnShellLoaded(object? sender, EventArgs e)
	{
		Loaded -= OnShellLoaded;

		// 加载历史对话
		await LoadChatHistoriesAsync();

		try
		{
			var token = await SecureStorage.GetAsync("token");
			if (!string.IsNullOrEmpty(token))
			{
				await GoToAsync("//chat");
			}
		}
		catch
		{
			// SecureStorage 读取失败，留在登录页
		}
	}

	protected override void OnNavigated(ShellNavigatedEventArgs args)
	{
		base.OnNavigated(args);

		// 每次导航时刷新历史对话列表
		if (args.Current.Location.OriginalString.Contains("chat"))
		{
			MainThread.BeginInvokeOnMainThread(async () => await LoadChatHistoriesAsync());
		}
	}

	private async Task LoadChatHistoriesAsync()
	{
		var conversations = await _historyService.GetConversationsAsync();
		ChatHistories.Clear();
		foreach (var conv in conversations)
		{
			ChatHistories.Add(new ChatHistoryItem
			{
				Id = conv.Id,
				Title = conv.Title,
				IsPinned = conv.IsPinned
			});
		}
	}

	private async void OnMenuItemSelected(object? sender, SelectionChangedEventArgs e)
	{
		if (e.CurrentSelection.FirstOrDefault() is MenuItem menuItem)
		{
			if (menuItem.Route == "chat")
			{
				// 开始新对话
				await _chatViewModel.StartNewChatAsync();
			}

			await GoToAsync($"//{menuItem.Route}");
			FlyoutIsPresented = false;

			if (sender is CollectionView collectionView)
			{
				collectionView.SelectedItem = null;
			}
		}
	}

	private async void OnMenuItemTapped(object? sender, EventArgs e)
	{
		if (sender is Grid grid && grid.BindingContext is MenuItem menuItem)
		{
			if (menuItem.Route == "chat")
			{
				// 开始新对话
				await _chatViewModel.StartNewChatAsync();
			}

			await GoToAsync($"//{menuItem.Route}");
			FlyoutIsPresented = false;
		}
	}

	private async void OnChatHistorySelected(object? sender, SelectionChangedEventArgs e)
	{
		if (e.CurrentSelection.FirstOrDefault() is ChatHistoryItem chatHistory)
		{
			// 加载选中的历史对话
			await _chatViewModel.LoadConversationAsync(chatHistory.Id);
			await GoToAsync("//chat");
			FlyoutIsPresented = false;

			if (sender is CollectionView collectionView)
			{
				collectionView.SelectedItem = null;
			}
		}
	}

	private void OnChatHistoryPointerPressed(object? sender, PointerEventArgs e)
	{
		if (sender is not View view || view.BindingContext is not ChatHistoryItem chatHistory) return;

		_longPressCts?.Cancel();
		_longPressCts = new CancellationTokenSource();
		var token = _longPressCts.Token;

		Task.Delay(LongPressMs, token).ContinueWith(t =>
		{
			if (t.IsCompletedSuccessfully)
				MainThread.BeginInvokeOnMainThread(() => ShowHistoryMenuAsync(chatHistory));
		});
	}

	private void OnChatHistoryPointerReleased(object? sender, PointerEventArgs e)
	{
		_longPressCts?.Cancel();
	}

	private async void OnChatHistoryTapped(object? sender, EventArgs e)
	{
		// 如果长按计时还在跑说明是短按，取消长按并导航
		_longPressCts?.Cancel();
		if (sender is Grid grid && grid.BindingContext is ChatHistoryItem chatHistory)
		{
			await _chatViewModel.LoadConversationAsync(chatHistory.Id);
			await GoToAsync("//chat");
			FlyoutIsPresented = false;
		}
	}

	private async void OnChatHistoryLongPressed(object? sender, EventArgs e)
	{
		if (sender is Grid grid && grid.BindingContext is ChatHistoryItem chatHistory)
			await ShowHistoryMenuAsync(chatHistory);
	}

	private async Task ShowHistoryMenuAsync(ChatHistoryItem chatHistory)
	{
		var pinLabel = chatHistory.IsPinned ? "取消置顶" : "置顶";
		var action = await DisplayActionSheet(chatHistory.Title, "取消", null, pinLabel, "删除");

		if (action == pinLabel)
		{
			await _historyService.TogglePinAsync(chatHistory.Id);
			await LoadChatHistoriesAsync();
		}
		else if (action == "删除")
		{
			bool confirm = await DisplayAlert("删除对话", $"确定删除「{chatHistory.Title}」？", "删除", "取消");
			if (confirm)
			{
				await _historyService.DeleteConversationAsync(chatHistory.Id);
				await _chatViewModel.OnConversationDeletedAsync(chatHistory.Id);
				await LoadChatHistoriesAsync();
			}
		}
	}
}

public class MenuItem
{
	public string Title { get; set; } = string.Empty;
	public string Route { get; set; } = string.Empty;
}

public class ChatHistoryItem
{
	public int Id { get; set; }
	public string Title { get; set; } = string.Empty;
	public bool IsPinned { get; set; }
}

