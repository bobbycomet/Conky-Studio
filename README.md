## Conky Studio

<div align="center">
  
<img width="300" height="300" alt="conky-studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

</div>

Conky is incredibly powerful, but creating and managing themes often requires editing Lua, Cairo, shell scripts, and Conky configuration files by hand. Conky Studio is a visual editor designed to make building, managing, and sharing Conky themes accessible without sacrificing flexibility.

Conky Studio is already capable of building real, fully functional themes, but I'm waiting to make a public release until the remaining core features are finished and the workflow is polished.

While the app is technically functional right now, I’m holding off on a public release until the core feature set is fully locked in.

### Key Features

* **Visual Node Editor:** Wire up custom logic, scripts, Lua, and Cairo effortlessly using a Blueprint-style workflow.
* **Built-in Theme Manager:** Automatically discovers themes in ~/.conky and ~/.config/conky, complete with previews, installation, duplication, exporting, and README support.
* **One-Click Control & Debugging:** Start themes directly from the app and monitor live execution logs to catch errors in real time.
* **Modular Plugin System:** Expand functionality with custom nodes or install community-made plugins.
* **Flexible Theme Importing:** Import themes via `.zip` or `.tar.gz` archives, through an integrated Community Store, or directly via OpenDesktop API integration (the OpenDesktop feature is currently in progress).
* **Custom Script Generator:** Easily create and attach custom scripts to your widgets by making it a custom node in the complex setting.
* **Live Preview & Debugging:** Launch a real Conky instance directly from Studio and monitor live logs to catch errors while designing.
* **Plugin System:** Extend Conky Studio with community-made nodes, generators, and tools without modifying the core application.

> **Note on Compatibility:** Why every theme uses start.sh. Every theme generated or managed by Conky Studio launches through a standard start.sh entry point. This provides a consistent way to start Conky, initialize background scripts, and manage runtime resources across Linux distributions. It also eliminates many command-line edge cases, making themes easier to install, share, and support.

Support Development

If you'd like to help make Conky Studio even better, consider sponsoring the project on GitHub. Your support helps me dedicate more time to development, bug fixes, documentation, and new features. 
[GitHub sponsors](https://github.com/sponsors/bobbycomet)

## Current Status

Conky Studio is under active development.

Already implemented:

- Visual node editor
- Live Conky preview
- Theme manager
- Code generation
- Import/export
- Community Store backend
- Plugin framework

Still in progress:

- OpenDesktop integration
- Layer/timeline editor
- Additional plugins
- Final workflow polish before public release

---


<img width="1920" height="1080" alt="Screenshot_20260725_215056" src="https://github.com/user-attachments/assets/4d0d4915-bd94-4923-8c38-1fe80f9086f4" />
<img width="1920" height="1080" alt="Screenshot_20260725_222200" src="https://github.com/user-attachments/assets/510d2054-f2ce-419b-85d5-35d40683fae6" />
<img width="1920" height="1080" alt="Screenshot_20260725_222334" src="https://github.com/user-attachments/assets/3d3baa56-acd3-4a68-a266-5cf910cb49b4" />
<img width="1920" height="1080" alt="Screenshot_20260726_004030" src="https://github.com/user-attachments/assets/64cc10d8-c1e0-43fe-aa68-3c6b804eb7fb" />
<img width="1920" height="1080" alt="Screenshot_20260726_004041" src="https://github.com/user-attachments/assets/38df8b6b-b835-4bd6-8fb0-edee46d89994" />
<img width="1920" height="1080" alt="Screenshot_20260726_004114" src="https://github.com/user-attachments/assets/2794cb57-9e23-4d8d-bfea-81b4fa3fd663" />
<img width="1920" height="1080" alt="Screenshot_20260726_004051" src="https://github.com/user-attachments/assets/36e43196-e09b-4b50-a361-649a8cc99fd4" />
<img width="1920" height="1080" alt="Screenshot_20260726_004103" src="https://github.com/user-attachments/assets/6792bb3c-7de6-4144-aba5-a18a53661970" />

## Themes I have made with this tool. If there is a red line, I was just redacting my location info.

<img width="1920" height="1080" alt="Screenshot_20260724_083124" src="https://github.com/user-attachments/assets/06c87d09-2b5a-466a-956b-00e8b84876f1" />
<img width="1920" height="1080" alt="Screenshot_20260724_181643" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />
<img width="1920" height="1080" alt="Screenshot_20260719_220545" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
