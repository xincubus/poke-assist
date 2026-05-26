using Android.App;
using Android.Content.PM;
using Android.Content.Res;
using Android.OS;

namespace PokemonApp;

[Activity(Theme = "@style/Maui.SplashTheme", MainLauncher = true, LaunchMode = LaunchMode.SingleTop, ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
public class MainActivity : MauiAppCompatActivity
{
    protected override void OnCreate(Bundle savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        SetNavigationBarColor();
    }

    public override void OnConfigurationChanged(Configuration newConfig)
    {
        base.OnConfigurationChanged(newConfig);
        SetNavigationBarColor();
    }

    private void SetNavigationBarColor()
    {
        var isDark = (Resources.Configuration.UiMode & UiMode.NightMask) == UiMode.NightYes;
        Window.SetNavigationBarColor(Android.Graphics.Color.ParseColor(isDark ? "#1f1f1f" : "#F5F5F5"));
    }
}
