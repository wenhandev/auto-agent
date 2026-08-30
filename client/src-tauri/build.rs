fn main() {
    let target = std::env::var("TARGET").expect("TARGET env var not set by Cargo");
    println!("cargo:rustc-env=TAURI_TARGET_TRIPLE={target}");
    tauri_build::build()
}
