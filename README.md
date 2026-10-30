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

The `Package Android SDK bundle and components` workflow reuses existing releases,
verifies their GitHub SHA-256 digests, and publishes a default bundle plus individual
component archives. It does not compile the native tools again.
Additional platforms come directly from Google's stable repository through the
runner's SDK Manager, which verifies the downloads and creates official package
metadata. Platforms contain architecture-independent files, so no ARM64 rebuild
is needed. Official minor-version directories such as `android-37.2` are preserved.
The workflow compiles a minimal Java Activity against every platform before packaging.

The default selection is maintained in `sdk-bundle.json`:

- Android Platforms API 30–36, 36.1, 37.0, 37.1, and 37.2.
- Build Tools 34.0.0, 35.0.0, 36.0.0, and 37.0.0.
- One Platform Tools and Command-line Tools installation from the base SDK.
- NDK and CMake remain separate distributions.

Every archive uses the standard `android-sdk/` root, preserves package metadata,
and includes the SDK licenses. Command-line tools use `cmdline-tools/latest/`.
The complete bundle contains the same components as the individual archives;
clients download the bundle for initial setup, then individual missing components.
Build Tools use real version directories rather than aliases between versions.

Each release includes `sdk-components-aarch64-linux-android.json` with component
IDs, revisions, installation paths, asset names, compressed sizes and SHA-256
hashes, plus `SHA256SUMS-aarch64-linux-android`. Release notes list actual sizes.
Component archives use a 16 MiB XZ dictionary. The complete bundle retains the
existing 256 MiB dictionary to compress repeated data across platform versions.

`Make SDK for Android (bionic arm64)` continues to build native binaries, now emits
component archives alongside each SDK, and assembles the default distribution
after all requested source builds succeed. The packaging workflow can also be
run independently when only the default selection or archive format changes.
