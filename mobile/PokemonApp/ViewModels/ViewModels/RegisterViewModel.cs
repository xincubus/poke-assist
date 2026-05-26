using System.Windows.Input;
using PokemonApp.Services;

namespace PokemonApp.ViewModels;

public class RegisterViewModel : BaseViewModel
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

    private string _confirmPassword = string.Empty;
    public string ConfirmPassword
    {
        get => _confirmPassword;
        set => SetProperty(ref _confirmPassword, value);
    }

    private string _errorMessage = string.Empty;
    public string ErrorMessage
    {
        get => _errorMessage;
        set => SetProperty(ref _errorMessage, value);
    }

    public ICommand RegisterCommand { get; }
    public ICommand GoToLoginCommand { get; }

    public RegisterViewModel(AuthService authService)
    {
        _authService = authService;
        RegisterCommand = new Command(async () => await RegisterAsync());
        GoToLoginCommand = new Command(async () =>
            await Shell.Current.GoToAsync("//login"));
    }

    private async Task RegisterAsync()
    {
        if (string.IsNullOrWhiteSpace(Username) || string.IsNullOrWhiteSpace(Password))
        {
            ErrorMessage = "请填写所有字段";
            return;
        }
        if (Password != ConfirmPassword)
        {
            ErrorMessage = "两次密码不一致";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;

        try
        {
            var success = await _authService.RegisterAsync(Username, Password);
            if (success)
            {
                await Shell.Current.GoToAsync("//login");
            }
            else
            {
                ErrorMessage = "注册失败，用户名可能已存在";
            }
        }
        catch (HttpRequestException)
        {
            ErrorMessage = "无法连接到服务器";
        }
        catch (Exception ex)
        {
            ErrorMessage = $"注册异常: {ex.Message}";
        }
        finally
        {
            IsBusy = false;
        }
    }
}
