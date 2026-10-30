# 中文说明

本 fork 在上游基础上新增一个 GitHub Actions 工作流(`build-arm64.yml`):
构建并发布 **aarch64-linux-android(bionic)** 目标的Android SDK (bionic aarch64) —— 面向在 Android
设备(Termux 等)上直接使用官方构建系统的场景。

- 使用: Actions → `Make SDK for Android (bionic arm64)` → Run workflow(可填版本/修订, 默认全量目标)
- 产物: 发布在本仓 Releases
- 构建容器、依赖与步骤完全沿用上游, 见上游 README 与 `docker/`、`scripts/`

## 致谢

- 上游: [HomuHomu833/android-sdk-custom](https://github.com/HomuHomu833/android-sdk-custom)
- 思路沿袭: [Lzhiyong/android-sdk-tools](https://github.com/lzhiyong/android-sdk-tools)

---

# English

This fork adds one GitHub Actions workflow on top of upstream
(`build-arm64.yml`): it builds and releases the **aarch64-linux-android
(bionic)** flavor of the Android SDK (bionic aarch64), for use on Android devices themselves
(Termux and alike).

- Usage: Actions → `Make SDK for Android (bionic arm64)` → Run workflow (version/revision inputs optional)
- Artifacts: published to this repository's Releases
- Build container, dependencies and steps are entirely upstream's — see the
  upstream README plus `docker/` and `scripts/`


## Android ARM64 发行结构

每个 `sdk-<Build Tools版本>` 发布 `android-sdk.tar.xz`、`build-tools.tar.xz`、
`platform-tools.tar.xz`、`cmdline-tools.tar.xz` 和 `SHA256SUMS`。
整包只包含自身 Build Tools、一个匹配 Platform 及公共工具，不混入其他 Build Tools。
例如 `sdk-35.0.0` 自带 Platform 35；`sdk-37.0.0` 使用官方 Platform 37.0。

Platform 单独发布为 `platform-<API>`，包含 `platforms.tar.xz` 和 `SHA256SUMS`。
例如缺少 Platform 34 时直接下载 `platform-34/platforms.tar.xz`。
API 小版本编号保留原样，例如 `platform-36.1`、`platform-37.0`。
所有归档解压到 `android-sdk/`，保留元数据和 licenses，使用 16 MiB XZ 字典。
无需额外组件清单；Build Tools 版本和 compileSdk 独立选择。

构建 Action 发布 SDK 与 Platform；独立 Platform Action 仅从 Google 获取官方数据并打包。
重新打包 Action 可以迁移旧发行包：先备份所有旧 Release、校验并保存新产物，
再执行显式选择的删除重建；备份 Actions artifact 保留 30 天，Git tag 保留。
常规发布不覆盖已有 Release。NDK、CMake 继续由各自仓库提供。
