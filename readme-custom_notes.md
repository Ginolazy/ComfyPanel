# ComfyPanel Custom Nodes for ComfyUI 🎨⚡
### To be updated
A powerful and thoughtfully designed collection of custom nodes for ComfyUI, covering **workflow control, image & mask processing, previews, and text utilities**.  
Built to make complex workflows **cleaner, faster, and more controllable**—with just a touch of fun ✨

---

## ✨ Features

- **Image & Mask Processing**  
  Blend, constrain, switch, swap, transform, and scale images and masks with precision and ease.

- **Process & Restore Workflows**  
  Crop images by mask, process them independently, and seamlessly restore them to their original positions—ideal for advanced inpainting pipelines.

- **Text & Numeric Utilities**  
  Perform math operations, concatenate strings, translate and transform text, and display values directly inside your workflow.

- **Inpainting Helpers**  
  Purpose-built nodes for cropping, stitching, extending, and restoring image regions without manual rewiring.

- **Workflow Control & Logic**  
  Powerful logic switches, previews, pauses, and automatic muting nodes that give you fine-grained control over execution flow—while saving compute behind the scenes 😏

---

## 🌟 Node Highlights

### 🔀 SwitchAnyMute, SwitchAnyCombo (Mute)

More than a simple data switch, **SwitchAnyMute, SwitchAnyCombo** provides **true execution-flow control**.

**Key feature**  
- 💤 **Upstream silence**  
  All unselected inputs keep their *entire upstream node chains fully inactive*. Only the selected branch executes.

**Why it’s awesome**  
- Eliminates unnecessary computation in heavy image or mask pipelines  
- Prevents unintended side effects from inactive branches  
- Makes complex workflows deterministic and easier to debug  
- Enables real conditional execution—like a mini program inside ComfyUI  

**Typical use cases**  
- Prompt / conditioning A–B testing  
- Switching between alternative image or mask processing paths  
- Debugging without deleting or muting nodes manually  
- Building performance-friendly, conditional pipelines  

**One-line summary**  
> **SwitchAnyMute, SwitchAnyCombo**: Only the selected branch runs—everything else stays muted 😎

---

### 🔇 AutoMute

Automatically mutes or unmutes nodes or groups based on monitored node states.

**Key feature**  
- 🤖 **Smart auto-control**  
  Target nodes or groups activate only when required and remain silent otherwise.

**Why it’s awesome**  
- Saves compute by preventing unnecessary execution  
- Integrates seamlessly with *Fast Groups Muter*
- Enables reactive, logic-driven workflows without extra wiring  

**Typical use cases**  
- Enable mask-processing groups only when masks are present  
- Keep previews and auxiliary nodes dormant until triggered  
- Build self-managing workflows that adapt automatically  

**One-line summary**  
> **AutoMute**: A silent guardian for your workflow—active only when needed 😎

---

### 👀 AnyPreviewPause

A versatile node for **previewing data and controlling execution**.

**Key features**
- 🖼️ **Image & mask pairing**
  Automatically pairs connected images and masks for grouped overlay previews (list-supported).  
- ⏸️ **Pause execution**
  Temporarily halt the workflow to tweak masks, prompts, or text before continuing.  
- ✨ **Flexible previews**
  Works with images, masks, and text.

**Why it’s awesome**  
- Inspect intermediate results without breaking the workflow  
- Perfect for interactive inpainting and prompt tuning  
- Makes debugging and experimentation safe and enjoyable  

**One-line summary**
> **AnyPreviewPause**: Preview, pause, and tweak—without losing control 😎

---

## 📦 Nodes

### 🖼️ Image & Mask

- `BlendByMask` – Blend two images using a mask  
- `ImageMask_Constrain` – Keep images and masks perfectly aligned  
- `ImageMask_Switch`, `ImageMask_SwitchAuto` – Dynamically switch images or masks  
- `ImageMask_Swap` – Swap two images or masks  
- `ImageMask_Transform` – Rotate and flip images or masks  
- `ImageBatchToImageList`, `ImageListToImageBatch` – Convert between batch and list formats  
- `MakeBatch` – Create image batches  
- `ScaleAny`, `ImageMask_Scale` – Resize images or masks  
- `SwitchMaskAuto` – Automatically select masks  
- `ImageBlank` – Generate a blank image canvas  
- `ImageFilterAdjustments` – Brightness, contrast, and tone controls  
- `ImageRemoveAlpha` – Remove alpha channels  
- `ImageSwap` – Swap images  
- `ImageMask_Composite` – Composite masks onto images

---

### 🔁 Process & Restore

- `CropByMask`, `CropByMaskRestore` – Crop by mask and restore seamlessly  
- `ImageConcat`, `ImageConcatRestore` – Concatenate images and restore layout  
- `ImageMask_Scale`, `ImageMask_ScaleRestore` – Scale images or masks and restore originals
- `FluxKontextImageCompensate` – Expands canvas to compensate for Kontext model stretching
- `FluxKontextImageRestore` – Restores image to original aspect ratio/composition, with optional pixel-perfect auto-alignment

---

### 📝 Text

- `Float`, `Int` – Basic numeric primitives  
- `MathOperationFloat`, `MathOperationInt` – Math operations  
- `StringListToString` – Join string lists  
- `TextConcat` – Concatenate text  
- `ShowText` – Display text in workflows  
- `TextMultiline` – macOS-only node integrating with Shortcuts for text translation and transformation ✨

---

### 🧠 Utilities & Logic

- `AnyPreview` – Preview images or text, optionally pause execution  
- `AnyPause` – Pause workflow execution  
- `AnyPreviewPause` – Paired previews + pause control  
- `SwitchAny`, `SwitchAnyMute`, `SwitchAnyCombo`, `SwitchAuto`, `SwitchOutput` –  
  Logic switch nodes that route any type of data with explicit control over execution and outputs
- `PrimitivePlus` – Manage and proxy multiple Primitive-style widgets from different nodes in a single control hub  
- `MakeAnyList` – Create lists of any data type  
- `AutoMute` – Automatically mute/unmute nodes or groups based on monitored states

---

## 🛠 Installation

1. Navigate to your ComfyUI `custom_nodes` directory  
2. Clone the repository:
   ```bash
   git clone https://github.com/Ginolazy/ComfyPanel.git
