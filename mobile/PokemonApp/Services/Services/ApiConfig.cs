namespace PokemonApp.Services;

/// <summary>
/// API 配置，后端地址在这里统一管理
/// </summary>
public static class ApiConfig
{
    // 开发时用本机地址，部署后改成服务器地址
    public static string BaseUrl { get; set; } = "http://8.136.224.24:8000";

    // 用户选择的模型（空字符串表示使用服务器默认值）
    // 对话模型：控制意图识别（Call #1）和结果总结（Call #3）
    public static string SelectedModel { get; set; } = "";
    // 计算模型：控制伤害计算参数提取（Call #2，Tool Use）
    public static string SelectedToolModel { get; set; } = "";
}
