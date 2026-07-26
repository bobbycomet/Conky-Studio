## Conky Studio

<div align="center">
  
<img width="300" height="300" alt="conky-studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

</div>

Conky can be difficult for users who don’t know how to code or simply want a hassle-free way to manage their setups. That is where **Conky Studio** comes in.

While still actively in development, Conky Studio is designed to streamline theme management and custom Conky creation using a visual node system inspired by Unreal Engine's Blueprints. In fact, it's the exact secret sauce behind how I build and iterate on my own custom themes so quickly.

While the app is technically functional right now, I’m holding off on a public release until the core feature set is fully locked in.

### Key Features

* **Visual Node Editor:** Wire up custom logic, scripts, Lua, and Cairo effortlessly using a Blueprint-style workflow.
* **Smart Directory Detection:** Automatically discovers themes stored in both `~/.conky` and `~/.config/conky/<folder>`, complete with README preview support.
* **One-Click Control & Debugging:** Start themes directly from the app and monitor live execution logs to catch errors in real time.
* **Modular Plugin System:** Expand functionality with custom nodes or install community-made plugins.
* **Flexible Theme Importing:** Import themes via `.zip` or `.tar.gz` archives, through an integrated Community Store, or directly via OpenDesktop API integration (the OpenDesktop feature is currently in progress).
* **Custom Script Generator:** Easily create and attach custom scripts to your widgets by making it a custom node in the complex setting.

> **Note on Compatibility:** Conky Studio relies on a start.sh entry point to execute scripts, so any custom or imported themes must follow this format. Standardizing execution through a script ensures themes launch reliably without syntax hiccups, and saves my issue tracker and Discord from being flooded with command-line edge cases.

---


<img width="1920" height="1080" alt="Screenshot_20260725_215056" src="https://github.com/user-attachments/assets/4d0d4915-bd94-4923-8c38-1fe80f9086f4" />
<img width="1920" height="1080" alt="Screenshot_20260725_222200" src="https://github.com/user-attachments/assets/510d2054-f2ce-419b-85d5-35d40683fae6" />
<img width="1920" height="1080" alt="Screenshot_20260725_222334" src="https://github.com/user-attachments/assets/3d3baa56-acd3-4a68-a266-5cf910cb49b4" />
<img width="1920" height="1080" alt="Screenshot_20260726_004030" src="https://github.com/user-attachments/assets/64cc10d8-c1e0-43fe-aa68-3c6b804eb7fb" />
<img width="1920" height="1080" alt="Screenshot_20260726_004041" src="https://github.com/user-attachments/assets/38df8b6b-b835-4bd6-8fb0-edee46d89994" />
<img width="1920" height="1080" alt="Screenshot_20260726_004114" src="https://github.com/user-attachments/assets/2794cb57-9e23-4d8d-bfea-81b4fa3fd663" />
<img width="1920" height="1080" alt="Screenshot_20260726_004051" src="https://github.com/user-attachments/assets/36e43196-e09b-4b50-a361-649a8cc99fd4" />
<img width="1920" height="1080" alt="Screenshot_20260726_004103" src="https://github.com/user-attachments/assets/6792bb3c-7de6-4144-aba5-a18a53661970" />
