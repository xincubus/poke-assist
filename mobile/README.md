# Mobile - 宝可梦助手安卓客户端

## 目录结构

```
mobile/
├── ui/                     # UI 原型（10个 HTML 页面）
├── README.md               # 本文件
└── PokemonApp/             # .NET MAUI 安卓客户端
    ├── Behaviors/           # 自定义行为
    │   └── LongPressBehavior.cs  # 长按手势行为（Android 用原生 LongClick，其他平台用 PointerGestureRecognizer + 计时器）
    ├── Controls/            # 自定义控件
    │   └── MarkdownLabel.cs # Markdown 链接内联点击控件（FormattedString + Span + TapGestureRecognizer，支持多链接）
    ├── Models/              # 数据模型
    │   ├── ChatMessage.cs   # 聊天消息（运行时，含流式支持、长按选择文本）
    │   ├── StoredChatMessage.cs  # 聊天消息（SQLite 持久化）
    │   ├── Conversation.cs  # 对话会话（SQLite 持久化）
    │   ├── PokemonInfo.cs   # 宝可梦信息（运行时）
    │   ├── StoredPokemon.cs # 宝可梦信息（SQLite 持久化）
    │   ├── TeamInfo.cs      # 队伍信息（运行时）
    │   ├── StoredTeam.cs    # 队伍信息（SQLite 持久化，成员 ID 逗号分隔）
    │   └── UserInfo.cs      # 用户信息
    ├── Views/               # XAML 页面
    │   ├── LoginPage        # 登录页
    │   ├── RegisterPage     # 注册页
    │   ├── ChatPage         # 对话页（主界面，支持流式逐字显示、MarkdownLabel 内联可点击链接、长按复制/选择文本）
    │   ├── DamageCalcPage    # 伤害计算器（WebView，侧边栏入口 + 聊天链接跳转，支持 URL 参数，宝可梦标签页内支持保存到"我的宝可梦"）
    │   ├── PokemonListPage  # 精灵列表（查看/添加/编辑/删除，本地 SQLite）
    │   ├── AddPokemonPage   # 添加/编辑宝可梦（名称搜索下拉、自动填充基础能力值/图片/特性、能力点数表格、性格/特性/道具下拉、4个招式槽；Android 用原生 TextWatcher 绕过 MAUI TextChanged suppress 问题）
    │   ├── TeamListPage     # 队伍列表（查看/创建/编辑/删除，本地 SQLite）
    │   ├── AddTeamPage      # 创建/编辑队伍（命名 + 从宝可梦列表多选成员，最多6只）
    │   └── SettingsPage     # 设置页
    ├── ViewModels/          # MVVM ViewModel
    │   ├── BaseViewModel.cs  # 基类（INotifyPropertyChanged）
    │   ├── ChatViewModel.cs  # 聊天逻辑（含 SSE 流式响应）
    │   ├── PokemonViewModel.cs  # 宝可梦列表逻辑（加载/删除）
    │   ├── TeamViewModel.cs     # 队伍列表逻辑（加载/删除）
    │   ├── LoginViewModel.cs
    │   └── RegisterViewModel.cs
    ├── Services/            # API 服务层
    │   ├── ApiConfig.cs          # 服务器地址配置
    │   ├── ChatService.cs        # 聊天服务（SSE 流式 + 普通请求，自动携带 platform=mobile）
    │   ├── AuthService.cs        # 用户认证服务
    │   ├── ChatHistoryService.cs # 聊天历史本地存储（SQLite）
    │   ├── PokemonStorageService.cs  # 宝可梦/队伍本地存储（SQLite）+ 服务器同步（保存/删除后自动同步）
    │   └── PokemonDbService.cs   # 宝可梦数据库查询（搜索宝可梦/招式/道具，调用后端 API）
    ├── Converters/          # XAML 值转换器
    │   └── Converters.cs    # InvertBool、StringToBool、BusyToButtonText
    ├── Platforms/           # 平台特定代码
    ├── App.xaml             # 应用入口（含全局资源和转换器注册）
    ├── AppShell.xaml        # Shell 导航配置（登录→底部Tab）
    ├── MauiProgram.cs       # DI 注册（服务、ViewModel、页面）
    ├── PokemonApp.csproj    # 项目文件
    ├── pokemon-app.keystore # Android 签名密钥库
    └── app/                 # APK 发布目录（下载接口自动取最新文件）
```

## 技术栈

- .NET 9 + MAUI（跨平台，主要目标 Android）
- MVVM 架构（Model-View-ViewModel）
- SSE（Server-Sent Events）流式响应，聊天逐字显示
- 后端对接 FastAPI（`api/` 目录）

## 环境要求

- .NET 9 SDK
- .NET MAUI workload（`dotnet workload install maui`）
- JDK 17+（编译 Android 需要）
- Android SDK（编译 Android 需要）
- Visual Studio 2022（推荐，需安装 ".NET MAUI" 工作负载）

## 用 Visual Studio 打开

1. 打开 Visual Studio 2022
2. 确保已安装 ".NET Multi-platform App UI 开发" 工作负载
   - 工具 → 获取工具和功能 → 勾选 ".NET Multi-platform App UI 开发"
   - 这会自动安装 Android SDK、JDK、模拟器等
3. 文件 → 打开 → 项目/解决方案 → 选择 `mobile/PokemonApp/PokemonApp.csproj`
4. 选择目标：
   - Windows Machine：直接运行 Windows 版本
   - Android Emulator：运行安卓模拟器版本（需要 Android SDK）

## 命令行编译

```bash
# Windows 版本（无需 Android SDK）
dotnet build -f net9.0-windows10.0.19041.0

# Android 版本
dotnet build -f net9.0-android

# 如果 JDK/SDK 路径需要手动指定
dotnet build -f net9.0-android \
  -p:JavaSdkDirectory="C:/Program Files/Microsoft/jdk-17.0.18.8-hotspot" \
  -p:AndroidSdkDirectory="你的Android SDK路径"
```

## 页面导航流程

```
开屏 → 登录 ↔ 注册
         ↓
    侧边栏导航（Flyout）
    ├── 对话（主界面，SSE 流式聊天）
    ├── 宝可梦（精灵列表，本地 SQLite）
    ├── 队伍（队伍管理，本地 SQLite）
    ├── 伤害计算器（WebView 加载 mobile.html）
    └── 设置（服务器配置、退出登录）
```

## 本地数据存储

宝可梦和队伍数据存储在设备本地 SQLite（与聊天历史共用同一个 `chat_history.db`）：

| 表 | 说明 |
|---|---|
| `pokemons` | 本地宝可梦配置（名称、图片、基础值、性格/特性/道具） |
| `teams` | 队伍（名称 + 成员 ID 列表，最多6只） |
| `conversations` | 聊天会话 |
| `chat_messages` | 聊天消息 |
