using System.Windows.Input;
using PokemonApp.Services;

namespace PokemonApp.ViewModels;

public class LoginViewModel : BaseViewModel
{
    private readonly AuthService _authService;

    private string _username = string.Empty;
    public string Username
    {
        get => _username;
        set => SetProperty(ref _username, value);
    }

    private string _password = string.Empty;
    public string Password
    {
        get => _password;
        set => SetProperty(ref _password, value);
    }

    private string _errorMessage = string.Empty;
    public string ErrorMessage
    {
        get => _errorMessage;
        set => SetProperty(ref _errorMessage, value);
    }

    public ICommand LoginCommand { get; }
    public ICommand GoToRegisterCommand { get; }

    public LoginViewModel(AuthService authService)
    {
        _authService = authService;
        LoginCommand = new Command(async () => await LoginAsync());
        GoToRegisterCommand = new Command(async () =>
            await Shell.Current.GoToAsync("//register"));
    }

    private async Task LoginAsync()
    {
        if (string.IsNullOrWhiteSpace(Username) || string.IsNullOrWhiteSpace(Password))
        {
            ErrorMessage = "请输入用户名和密码";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;

        try
        {
            var user = await _authService.LoginAsync(Username, Password);
            if (user != null)
            {
                try
                {
                    await SecureStorage.SetAsync("token", user.Token ?? string.Empty);
                    await SecureStorage.SetAsync("username", user.Username ?? string.Empty);
                }
                catch
                {
                    // Android Keystore 损坏时清除后重试
                    SecureStorage.RemoveAll();
                    await SecureStorage.SetAsync("token", user.Token ?? string.Empty);
                    await SecureStorage.SetAsync("username", user.Username ?? string.Empty);
                }
                await Shell.Current.GoToAsync("//chat");
            }
            else
            {
                ErrorMessage = "用户名或密码错误";
            }
        }
        catch (HttpRequestException)
        {
            ErrorMessage = "无法连接到服务器";
        }
        catch (Exception ex)
        {
            ErrorMessage = $"登录异常: {ex.Message}";
        }
        finally
        {
            IsBusy = false;
        }
    }
}
