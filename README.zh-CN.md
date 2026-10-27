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
