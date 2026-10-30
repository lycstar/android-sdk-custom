# Android SDK Custom

**Android SDK Custom** is a custom-built Android SDK that replaces the default binaries with rebuilt ones.

It integrates alternative libc implementations like **musl** (via **[Zig](https://ziglang.org/)**), **Bionic** (from the official Android NDK), **[llvm-mingw](https://github.com/mstorsjo/llvm-mingw)** and the macOS SDK (via **[osxcross](https://github.com/tpoechtrager/osxcross)**) to provide a more flexible and portable build environment.

This project is inspired by [lzhiyong's Android SDK Tools](https://github.com/lzhiyong/android-sdk-tools).

---

## 🚀 Features

- Custom-built binaries, sourced from Google's Android SDK repositories.
- Built using various toolchain's libc for improved portability and consistency.

---

## 🧭 Architecture & Platform Support

### 🔹 Zig-based Environment

**Platforms**
- Linux
- Android
- NetBSD
- FreeBSD
- OpenBSD

**Architectures**
- **X86 Family**: `x86`, `x86_64`, `x32`
- **ARM Family**: `arm`, `armeb`, `aarch64`, `aarch64_be`
- **RISC-V**: `riscv32`, `riscv64`
- **PowerPC**: `powerpc`, `powerpc64`, `powerpc64le`
- **MIPS**: `mips`, `mipsel`, `mips64`, `mips64el`
- **Thumb**: `thumb`, `thumbeb`
- **Other**: `loongarch64`, `s390x`, `sparc64` ,`hexagon`

---

### 🔹 Native Environment

**Platforms**
- Windows
- macOS
- Android

**Architectures**
- `x86`, `x86_64`
- `aarch64`
- `armv7` *(Android and Windows only)*
- `arm64ec` *(Windows-only)*
- `arm64e`, `x86_64h` *(macOS-only)*

---

## 🧰 Usage

This custom SDK works as a **drop-in replacement** for the standard Android SDK.<br>
Simply extract the archive and use it in your build setup just as you would with the official version.

---

## ⚖️ License

This project is licensed under the **MIT License**.<br>
See the **[LICENSE](LICENSE)** file for more details.

---

## 💬 Contributing
Feel free to open pull requests or issues if you have any contributions or feedback!

## Android ARM64 distribution

Each `sdk-<Build Tools version>` release contains fixed asset names:

```text
sdk-35.0.0/
  android-sdk.tar.xz       # one Build Tools version + matching Platform + shared tools
  build-tools.tar.xz       # build-tools/35.0.0/
  platform-tools.tar.xz
  cmdline-tools.tar.xz
  SHA256SUMS

platform-35/
  platforms.tar.xz         # platforms/android-35/
  SHA256SUMS
```

All archives extract into `android-sdk/`, retain package metadata and licenses,
and use a 16 MiB XZ dictionary. Command-line tools use `cmdline-tools/latest/`.
The SDK bundle contains only its own Build Tools and matching Platform (35 for
35.0.0; the official 37.0 platform for 37.0.0). Build Tools and compileSdk remain
independent project requirements; additional Platforms are installed separately.
Official minor IDs are preserved, e.g. `platform-36.1` and `platform-37.0`.
NDK and CMake remain separate distributions.

Clients derive download paths from the required version and verify `SHA256SUMS`:
`/releases/download/sdk-35.0.0/build-tools.tar.xz` or
`/releases/download/platform-35/platforms.tar.xz`. No component manifest is needed.

- `Make SDK for Android (bionic arm64)` compiles native tools and publishes separate
  SDK and Platform releases. Each matrix entry specifies its exact Build Tools
  and matching Platform; there is no aggregate bundle copied into version tags.
- `Package official Android Platforms` downloads selected official SDK data using
  Google's SDK Manager and publishes `platform-<API>` releases without rebuilding
  native tools. It compiles a minimal Activity against each Platform first.
- `Repackage Android ARM64 SDK releases` converts an existing bundle into these
  releases. Its migration option backs up all old assets, verifies all replacements,
  uploads both sets as recoverable Actions artifacts, then deletes and recreates
  releases. Git tags are retained. Backups are retained for 30 days.

Normal publishing preserves existing releases rather than overwriting them.
The destructive replacement option is for explicitly requested migrations only.
ARM64 ELF and archive checks do not replace Android-device execution tests.
