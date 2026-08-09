# Help — NFT Prompt Builder

**w3ir.io** · an online app for creating NFT collections: from idea and prompts to images, metadata and **mint-ready content**. The app itself does not mint — you **export a bundle** and mint on the platform of your choice (in-app minting stays optional).

- **Site:** https://ai.w3ir.io  
- **Interface languages:** Ukrainian / English (switcher in the left sidebar).  
- **NFT language:** prompts, `name`, `description` and `attributes` in metadata are in **English** (for OpenSea and other marketplaces).  
- **Support:** w3ir@pm.me

> This help is shown in the **📖 Help** tab. You can download it with the button at the top of the tab.

---

## 1. Quick start

### What you need

| What | Why |
|---|---|
| A browser (Chrome, Firefox, Edge) | to use the app |
| **MetaMask** / **Coinbase** (EVM) or **Phantom** (Solana) | **app sign-in** via SIWE signature (gasless) on the login screen |
| A **MetaMask** / **Phantom** wallet + the **Base** network | credits and USDC payment (💳 Credits stage) |
| A little **ETH on Base** (EVM) | for the 5 welcome credits (Sybil protection) and for gas when minting |

You do **not** need to install Python, API keys or anything on your computer — everything runs in the browser.

### App sign-in (SIWE)

The app is protected by **wallet sign-in** (Sign-In with Ethereum). When you open **https://ai.w3ir.io** you will see a split-screen login titled "Connect to Mint":

1. Click **Connect Wallet** and pick a wallet: **MetaMask** / **Coinbase** (EVM) or **Phantom** (Solana).
2. **Sign the message** in your wallet — this is **free, gasless and not a transaction**, just proof that you own the address.
3. After signing, the app unlocks.

> This is the **same sign-in** used for credits and generation: the wallet you sign in with automatically becomes your billing wallet — **no second signature at the 💳 Credits stage** (your balance binds immediately).
> No wallet? The login screen has a **"Request beta access"** link. Wallet sign-in is the only barrier; no email code is required.

### First steps (recommended path)

After your first sign-in you see **Welcome** (“Where to start?”):

| Button | Scenario |
|---|---|
| **🚀 1 NFT (1/1)** | *1/1 Fine Art* template → one prompt |
| **📦 Mini-drop 25** | *Abstract Geometry Series* (5×5 abstract); admins — *W3IR Showcase Demo* |
| **🌄 / 🎫 / 🏷️** (second row) | *Atmospheric Worlds*, *Event Badge*, *Brand Icon System* |
| **⚙️ Advanced mode** | Classic: Traits, Batch, Collection |
| **▶️ Continue last project** | if you already have autosave in **📂 Project** |

Return to Welcome: sidebar → **🏠 Choose your path**.

1. Open **https://ai.w3ir.io** and **sign in with your wallet** on the login screen (**Connect Wallet** → gasless signature).
2. In the **sidebar** choose the **"⛓️ Pipeline"** path.
3. The **⛓️ Pipeline** tab → **💳 Credits** stage → **Connect MetaMask** or **Phantom** → sign the message.
4. Go to the **1️⃣ Text** stage → generate prompts.
5. **2️⃣ Images** → pick an engine → run the queue → in the **curator** mark the good ones → **Save and go to export** (the export queue fills automatically).
6. **3️⃣ Export** → pick a platform → **build the bundle** (ZIP or IPFS folder). You mint on your chosen marketplace/tool (optionally via "Advanced").

Above the tabs there are **hints** (blue/green lines) — they point to the next step.

### Minimal 15-minute demo flow

If this is your first test, do not start with a large supply. Run a short cycle:

1. In the sidebar apply the **W3IR Showcase Demo** template or enter a simple idea: `neon owl alchemist`.
2. At **1️⃣ Text**, generate 5–10 prompts in **Matrix** mode or paste your own lines.
3. At **2️⃣ Images**, choose **Flux.1** or **Stability AI** for an inexpensive pilot.
4. Generate a **Pilot** or the first 3–5 images, rate them in the curator, approve 1–2 best results.
5. At **3️⃣ Export**, build a ZIP for **thirdweb** or **OpenSea** and open the archive: it should contain images, metadata and a README.

After this dry-run it is safer to generate 25/100/1000 NFTs: you know which style works, which engine fits, and how many credits you need.

---

## 2. Two working modes

In the **sidebar** → **🧭 Working mode** you can choose one of the paths.

### ⛓️ Pipeline (recommended on ai.w3ir.io)

The full cycle for a Web3 drop using **credits**:

```
💳 Credits → 1️⃣ Text → 2️⃣ Images (+ curator) → 3️⃣ Export
```

- Image generation deducts **credits** from your balance.
- You can start from ready prompts, your own images, or walk through to export step by step.
- The terminal action is **exporting a mint-ready bundle** for the chosen platform; in-app minting is optional.
- Tab: **⛓️ Pipeline** (stage switcher at the top).

Choose the pipeline when:

- you want to go quickly from idea to a ready ZIP;
- you do not want to enter your own OpenAI/Anthropic keys;
- you need curator review, Prompt-Lock, IPFS and marketplace formats;
- you are using the beta/public flow on `ai.w3ir.io`.

### 🏭 Collection (classic path, advanced)

The full generative cycle for deep work with **traits**, batches of up to 200 prompts and collections up to 10,000 tokens:

```
Idea → Traits → Batch → Collection → Quick preview → ZIP / IPFS · your API key
```

- **Prompts (Builder, Batch, Collection):** your OpenAI/Anthropic key (USD billed by the provider) + on **ai.w3ir.io** also **1 credit per LLM request**.
- **⑤ Quick preview:** your **OpenAI key** + on **ai.w3ir.io** **4 credits per frame** (separate from USD on your OpenAI account). **Not** a mint-ready drop — test 1–4 PNGs only.
- **④ Collection → bulk images:** your OpenAI key and a **USD budget** in that tab (platform credits are **not** charged).
- Full-cycle output is a **mint-ready bundle**: ZIP or IPFS (Pinata).
- From **Batch** or **Collection** you can click **"→ To Pipeline"** and continue with generation/export in the pipeline.

Choose the classic path when:

- you have your own API keys and want fine-grained control of provider costs;
- you need large trait matrices, checkpoints and resuming long runs;
- you prepare the collection gradually: prompts/metadata first, then images/IPFS.

### Choosing the right path

| Situation | Recommendation |
|---|---|
| First product test | **Pipeline**, 5–10 prompts, inexpensive engine |
| 25 NFT showcase | **Pipeline** + Pilot + curator |
| **100–10,000** NFT drop (traits, rarity) | **Classic → Collection** → **"→ To Pipeline"** — see **§ 5.1** |
| Large generative matrix (prompts only) | **Collection**, then bridge to pipeline |
| Abstract / geometry **25–100** | **Pipeline** + *Abstract Geometry Series* template |
| Abstract / geometry **500+** | **Classic → Collection** (2–3 trait axes), then pipeline |
| **Brand / community drop 25** | **Pipeline** + *Brand Icon System* template — see **§ 4.1.2** |
| **Linear sign system 25** | **✒️ Line Art Monograms** — single-weight monoline, **§ 4.1.2** |
| **Flat-vector PFP with clear slots** | **🟡 Flat Vector Mascots** — 6 object slots, **§ 4.1.0** |
| **Brand mascot 50–100** variants | **Style Bible** + matrix — **§ 4.1.2** |
| **Landscape / atmospheric 25** | **🌄 Atmospheric Worlds** — **§ 4.1.3** |
| **Event / POAP 25** | **🎫 Event Badge Series** or **🏛️ Art Deco Medallions** — **§ 4.1.4** |
| **Fine art / 1/1** | **🎨 1/1 Fine Art** or **🖋️ Sumi-e Ink Studies** — **§ 4.1.5** |
| **Abstract 25** | **🔷 Abstract Geometry** or **📺 Glitch Geometry** — **§ 4.1.8** |
| **Synthwave / retro PFP** | **🌅 Synthwave Retro** — **§ 4.1.6** |
| **Chibi / kawaii PFP 25** | **🍡 Chibi Champs** — **§ 4.1.8** |
| **Vinyl toy / designer toy** | **🧸 Vinyl Toy Squad** — **§ 4.1.8** |
| **Retro poster / no characters** | **🛸 Retro Poster Series** — **§ 4.1.8** |
| **Editorial chrome fashion** | **✨ Chrome Fashion Icons** — **§ 4.1.8** |
| **Art Deco event medals** | **🏛️ Art Deco Medallions** — **§ 4.1.8** |
| **Any mini-drop (~25)** | Full beginner recipes — **§ 4.1.8** (all templates) |
| **Explore many art styles on one hero** | Stage 1 **Specific group** — **§ 4.1.6** |
| You already have images | **Pipeline → 3️⃣ Export**, upload JPG/PNG |
| You only need metadata/CSV | **Collection → Batch** or Export Center in the pipeline |

---

## 3. Sidebar

| Element | What for |
|---|---|
| **Interface language** | 🇺🇦 / 🇬🇧 |
| **Working mode** | 🏭 Collection (own API key) or ⛓️ Pipeline (credits) |
| **💳 Credits** | balance and top-up (USDC on Base via Helio) |
| **📂 Project** | **active drop workspace** — autosave on disk; **My projects** dropdown; **➕ New**, **📋 Duplicate** (fork; copies all PNGs), **⬇️ Download** (ZIP to your PC), **✏️ Rename**, **🗑️ Delete** |
| **Collection templates** | 35 presets — 34 public (BAYC, Flat Vector Mascots, Brand Icon, Line Art Monograms, Atmospheric Worlds, Event Badge, Abstract Geometry, etc.) + admin-demo → "Apply template" fills in the base object, style, traits and series fixators (**§ 4.1.0**). **1k+ / 10k+** labels = large drop (Classic → Collection); **~N mini** = quick pipeline |
| **⚙️ Generation options** (expander) | traits, negative prompt, collection size; in **classic mode only** — nested **Constructor config export (JSON)** for manual idea/traits snapshots (separate from workspace autosave) |
| **💰 Drop cost calculator** | how many credits and which Helio package you need for a given supply |
| **💸 Spent this session** | estimated **your API key** spend in USD — **classic mode only** (hidden in pipeline/credits mode) |

On **ai.w3ir.io** the own-OpenAI-key fields are usually **hidden** — pipeline generation runs on credits.

**Pipeline workspace (📂 Project)** saves automatically after key steps: prompts, images, curator ratings, approved queue, Style Bible. Data lives on the server under your wallet — you can **return tomorrow**, pick the project from **My projects**, and continue or **Duplicate** to explore another line without touching the original. **Duplicate copies all PNGs** and uses disk space; delete unused drops with **🗑️**. With many projects (15+ by default) you'll see a soft warning. Hard limits (project count / disk MB) are optional server settings — paying users are exempt from the **project count** cap when enabled.

**⬇️ Download** packs the project into a ZIP (prompts, state, all PNGs) onto **your PC**. Important: the server **does not back up generated images** — the local ZIP is your full backup of the work; we recommend downloading after finishing a drop. It is a raw project snapshot, not a mint-ready bundle (that's Stage 3 / Export Center); opening the ZIP back in the app is not supported yet.

History, previews and matrix templates are also saved **per wallet**. In **classic mode**, optional **Constructor config export (JSON)** in the generation-options expander is a separate manual snapshot — not the same as **📂 Project** autosave. If you sign in with another wallet, lists will differ — that protects users on a shared server.

---

## 4. Pipeline — in detail

The **⛓️ Pipeline** tab. At the top there are counters: **Prompts · Generated · Approved · Queued**.

Stage switcher — **clickable pills** with a ✓ on completed ones: **💳 Credits · 1️⃣ Text · 2️⃣ Images · 3️⃣ Export** (credits first — a wallet and balance are needed before generation). The **"Next →"** button skips completed/locked stages. **Export** is reachable as soon as your wallet is connected — approve content on stage 2 or upload your own on stage 3.

### 4.1 Stage 1️⃣ — Text

Prompt structure: **base object → style → traits → details → series fixators → engine tags**.

The first two parts and the last one stay **identical across the whole collection** — they are
what makes 25 images a series rather than 25 separate drawings. Details — **§ 4.1.0**.

| Mode | Result |
|---|---|
| **Single** | one prompt |
| **Specific group** | one subject in several styles |
| **Matrix** | combinations from the lists (e.g. 5×5 = 25 prompts); axis labels follow the template **archetype** (PFP / Form×Background / Scene×Mood, etc.). A template with **three or more** trait categories is assembled **layer by layer**: every item gets one value from **each** category (headwear + eyewear + outfit + …), not just one overall — see **§ 4.1.0** |
| **✨ Generate N archetypes** | (expander in **Matrix**) LLM from theme → fills the first axis; for abstract — **“N motifs”** |
| **Custom text** | paste ready prompts (one per line), no builder |
| **Image-to-Prompt** | upload an image → get a prompt formula (vision) |

After generating on Stage 1, click **Next → Stage 2** (or the pills at the top) to open Style Bible.

**Tip:** for a **25 NFT** mini-drop use sidebar templates or Welcome. **Full beginner guide per template — § 4.1.8**. After **Apply template**: prompts, Style Bible, **Style lock** and negative are set from the archetype. Style catalog — **§ 4.1.6–4.1.7**.

**Where to edit traits after a template (Pipeline):** open **Stage 1 → Matrix** (not “Single”) — multiselect lists are filled from the template; the **Prompts** counter at the top should be > 0. The **② Traits** tab is **hidden** in Pipeline mode — for 1k+ generative drops and manual rarity weights, enable **Advanced mode** (see **§ 5 → ② Traits**).

**Collection archetypes** (`archetype` on each template): `pfp`, `abstract_geometric`, `landscape`, `event_badge`, `brand_icon`, `fine_art`. They change Stage 1 matrix labels, EN metadata traits, and Stage 2 quality presets.

Practical prompt rules:

- one prompt = one future token or one candidate image;
- write the main content in English, even if the UI is Ukrainian;
- do not mix several unrelated characters in one line if you want a predictable collection;
- lock stable things in **Style Bible**: style, lighting, camera, background, forbidden elements;
- for a matrix, a few good trait lists are better than dozens of random words.

Example of a simple line:

```text
cyber owl alchemist, emerald goggles, neon laboratory, centered NFT portrait, clean background
```

Example of matrix thinking: `Core = owl / fox / robot`, `Accessory = goggles / crown / plasma staff`, `Background = neon lab / moon temple / cyber forest`. This gives controlled combinations instead of a chaotic list.

### 4.1.0 Why a collection looks like a series (and not 25 different pictures)

Every model call is **independent** — it does not remember what it drew for the previous item.
Consistency therefore never happens on its own; it has to be stated in the prompt. The generator
does this for you with three parts that **stay the same** across every item of the collection.

| Part | What it is | Example |
|---|---|---|
| **Base object** | species/object, crop, proportions, character of lines and surface | `a single cartoon ape character, head and shoulders only, identical head shape and shoulder width, flat uniform fur tone, thick even outlines` |
| **Style + angle** | the style preset and fixed viewing angle from the template | `2D Vector Clean` · `Close-up PFP` |
| **Series fixators** | framing and lighting — the tail of the prompt | `centered composition, square format, subject fills the same portion of the frame, consistent lighting across all variations` |

Only **traits** change — and those are exactly what becomes rarity attributes in the metadata.

**The base object matters most.** It is not the collection's name but a description of what must
stay **the same**. Compare:

```text
❌ unique collector ape          → the model invents new anatomy and line weight every time
✅ a single cartoon ape character, head and shoulders only, identical head shape
   and shoulder width, flat uniform fur tone, thick even outlines
```

The formula to write your own: **[one subject] + [crop] + [what is fixed in proportions] +
[what is fixed in surface/lines]**. Write it in English and keep it to ~15–22 words: an overlong
base object pushes the fixators out of the prompt (the model's text window is finite, and it is
the tail that gets cut).

**Every item carries all of its layers.** A template with three or more trait categories is
assembled layer by layer: an item gets headwear **and** eyewear **and** an outfit **and** an
accessory **and** a background **and** an expression — one value from each category. This is what
rarity rests on: rarity is computed from **several** traits co-occurring in one item, so an item
with a single trait makes the rarity report meaningless.

**What you edit.** After **Apply template** the base object and fixators are already filled in for
the archetype — you do not have to touch them. For your **own** collection: replace the **idea**
with your own base object using the formula above, and lock the constants (style, lighting,
camera, forbidden elements) in **Style Bible** on Stage 2.

**Common mistakes:**

- a base object that is a two-word label — the most common reason for "why are they all different";
- several different subjects in one line (`ape and fox`) — the model will blend them unpredictably;
- changing style or angle mid-drop — the series falls apart even with a perfect base object;
- describing framing inside the base object (`centered`, `square format`) — it duplicates the
  fixators and only takes weight away from the object itself.

### 4.1.1 A collection of many characters in one style (e.g. 50)

Two common goals look similar but use **different** Stage 1 setups:

| Goal | What you get | Typical setup |
|---|---|---|
| **A. Many different characters** | cyber samurai, space wizard, neon cat… — **50 different subjects** | Matrix **50×1** or **10×5**, or **Custom text** (50 lines) |
| **B. Many variants of one hero** | one archetype (e.g. cyber samurai), **50 outfits / moods / backgrounds** | Sidebar **template** or matrix **1×50** |

The app **does not** mint and **does not** turn one uploaded photo into 50 copies (img2img is not in scope yet). It builds **text prompts**, then generates images from them. **Style Bible** keeps the look consistent; **traits** in the matrix become `attributes` in metadata.

#### What is automated today

| Feature | What it does |
|---|---|
| **Sidebar template → Apply** | Fills **Style Bible** and builds a **prompt matrix** from the template trait table (e.g. Cyberpunk PFP → hundreds of combos on one base idea). |
| **Matrix mode** | Cartesian product of categories: `Character × Background × Accessory`. The **Matrix combinations** metric shows the count **before** generation. |
| **✨ Rich prompts (LLM polish)** | Rewrites existing prompts in a **consistent style** + negative prompt; **does not invent** new character names. ~**1 credit per ~15 prompts**. |
| **✨ Generate N archetypes (Matrix)** | LLM from collection theme → **N unique English names** in the first matrix axis (for abstract — “motifs”). ~**1 cr / 15 names**. Requires OpenAI key. |
| **Custom text** | Paste ready prompts — **one line = one token**. Good for a list of 50 archetypes from a file or external LLM. |
| **Classic path (Collection tab)** | Trait tables + random sample of **N** unique combinations (`Traits → Batch → Collection`). |

There is no separate “generate 50 names” screen — use the **✨ Generate N archetypes** expander in **Matrix** mode (Stage 1). Requires an **OpenAI key** in the sidebar (🤖 AI & keys) plus platform credits (~1 cr / 15 names).

#### Recipe A — 50 **different** characters, one visual style

1. **Style Bible (Stage 1)** — lock what must stay the same for the whole drop:
   - **Style** — e.g. `anime cel-shaded, bold outlines, vibrant colors`
   - **Lighting / Camera / Background rule** — e.g. soft studio light, PFP close-up, solid gradient background
   - Click **💾 Save bible**
2. **Build the list of 50 subjects** (pick one path):
   - **✨ Generate N archetypes:** theme (e.g. `cyber animal collectors`) → N=50 → fills **Character variants**; **Background** — 1 shared value → **Combinations = 50**
   - **Matrix:** category **Character variants** — select or type **50** archetypes manually; **Background** — **1** shared value (e.g. `solid purple gradient`); **Accessory** — empty or 1 shared item → **Combinations = 50**
   - **Math instead of 50 lines:** e.g. **10 characters × 5 backgrounds = 50** (different heroes, shared palette via Bible)
   - **Custom text:** one archetype per line (50 lines), then **📥 Use these prompts**
3. **✨ Rich prompts** (recommended) — same tone across all 50 lines.
4. **Stage 2:** enable **Style lock**; engine **Flux.1** (economical) or **GPT Image** (premium); tier **Draft** first.
5. **🧪 Pilot** (~5–10 images) → check stars and engine → **🚀 Start generation (50)**.
6. **Curator** → **Save and go to export** (straight to **Stage 3**).

**Bulk list without typing each name:** **✨ Generate N archetypes** in Matrix **or** external ChatGPT → **Custom text** → Rich prompts.

Example fragment for Custom text:

```text
cyber samurai
space wizard
neon cat
crystal golem
plasma pirate
…
```

#### Recipe B — 50 **variants of one** character (same context)

Best when the collection is “one species / one hero, many traits” (BAYC-style, Cyberpunk PFP).

1. **Sidebar → template** (e.g. **🌃 Cyberpunk PFP** or **🐵 BAYC-style PFP**) → **Apply**.
   - Style Bible and a large trait matrix are created automatically from the template.
2. **Stage 2** → set **Limit** to **50** (or run Pilot first, then the full queue).
3. Optional manual matrix instead of a template:
   - **Character variants:** one line — `cyber samurai`
   - **Background:** 10 options
   - **Accessory:** 5 options → **1×10×5 = 50** variants of the **same** hero.

**Specific group** mode (one object × many **art styles**) gives 50 **stylistic** interpretations, not trait variants — usually worse for a uniform PFP drop than a template or trait matrix.

#### Image-to-Prompt — how it fits

**Image-to-Prompt** extracts a **text formula** from one reference image (vision). It does **not** produce 50 images from that file. Use it to **copy style/lighting** into Style Bible, then build the matrix or Custom text list as above.

#### Credits (rough guide, Draft tier)

| Engine | ~50 images |
|---|---|
| **Flux.1** | ~50 credits |
| **Stability AI** | ~50 credits |
| **GPT Image** | ~200 credits |
| **Rich prompts** (50 lines) | ~4 credits |
| **Image-to-Prompt** (optional) | 1 credit |

Failed generations are **refunded**; Pilot saves credits if the style needs tweaking.

#### Quick cheat sheet

```text
50 different heroes, one style:
  Style Bible → Custom text (50 lines) or Matrix 50×1
  → Rich prompts → Pilot → Batch 50 → Curator → Export

50 variants of one hero:
  Sidebar template → Apply → Stage 2 Limit 50
  → Pilot → Batch → Curator → Export
```

### 4.1.2 Brand collection: mark, mascot, community drop

For **Web3 brands, events, DAOs and communities**: one **visual identity** in many variants
(background, layout, material) — not random PFP characters.

#### What the app does and does not promise

| Possible today | Not guaranteed yet |
|---|---|
| **25–100** consistent variants via **Style Bible** + matrix | Pixel-perfect copy of an **uploaded** SVG/PNG logo |
| **Similarity** of mark/mascot across contexts | Legal sign-off like a Fortune 500 brand manual |
| **Curator** + export preflight before mint | Automatic trademark checking |

Generation is **text → image**. Each frame redraws the mark; for **best recognition**, limit
variation to **2–3 axes** and run **Pilot + curator**.

#### Two typical scenarios

| Scenario | Supply | Path |
|---|---|---|
| **A. Mini brand drop** (icons, social cards) | **25** | Sidebar → **🏷️ Brand Icon System** → Pipeline → Pilot → export |
| **A2. Linear sign system** (monograms) | **25** | Sidebar → **✒️ Line Art Monograms** → same path, monoline without fills |
| **B. Mascot × context** (merch, events, seasons) | **50–100** | Style Bible + matrix **1×N×M** or **Custom text** → **§ 4.1.1** |

**Which of the two brand templates.** *Brand Icon System* — filled flat shapes (app icon, social
card). *Line Art Monograms* — a single-weight monoline with no fills: right for monograms, seals
and "thin" identities. In the latter the series is held together not by the silhouette but by
**metrics** — constant stroke weight and optical size; keep them identical across items.

#### Recipe A — 25 variants (Brand Icon System template)

1. **Sidebar → 🏷️ Brand Icon System → Apply**.
2. **Idea** — replace with an **English** description of your mark (shape, colors, bans):
   ```text
   minimal geometric owl mark, two-tone navy and gold, no text, no photorealism
   ```
3. **Style Bible (Stage 1)** — lock style, lighting, **background rule**, negative
   (`no random text`, `no watermark`, `no extra logos`).
4. **Stage 2:** engine **GPT Image** (type/mark); **Pilot 5–10** → curator **≥4★** → full run.
5. **Export** — check preflight; collection `name`/`description` in **English**.

#### Recipe B — 50–100 variants of one mascot

1. **Style Bible** — one look for the whole drop (as in **§ 4.1.1**, recipe B).
2. **Matrix:** **Character variants** = one line (your mascot); **Background** = 10 values;
   **Layout** = 5 contexts → **1×10×5 = 50**.
3. **Rich prompts** — even tone; **do not** inject random brand copy into prompts.
4. Pilot → batch → curator → export.

#### Image-to-Prompt for brands

Upload a **reference** (sketch, moodboard, legacy logo) → **Image-to-Prompt** transfers
**style and composition into text** for the Style Bible. This is **not** img2img — no 50 copies
of the file. Full file-locked logo workflow is on the roadmap (**reference image / img2img**,
after E6 stabilizes).

#### Legal and quality

- You are responsible for **rights** to the mark and collection content.
- Do not generate third-party trademarks, competitor brand names, or fake partnerships.
- For client drops: agree on a **minimum curator bar** (e.g. ≥4★ only).

#### Cheat sheet

```text
25 brand icons:
  Brand Icon System → edit idea (EN) → Style Bible → GPT Image Pilot
  → Curator → Export

50 mascot contexts:
  Style Bible → Matrix 1 hero × 10 backgrounds × 5 contexts
  → Rich prompts → Pilot → Batch → Curator → Export
```

### 4.1.3 Atmospheric worlds (landscape)

Collections **without characters in frame**: landscapes, worlds, covers, 1/1 art. Best at **25**
frames (5 scenes × 5 lighting moods).

#### Template 🌄 Atmospheric Worlds

1. **Sidebar → 🌄 Atmospheric Worlds → Apply** (25 matrix prompts on Stage 1).
2. **Idea** — optionally refine the setting in English (`alpine fantasy`, `solarpunk coast`…).
3. **Style Bible** — lock style and ban people in negative:
   `no people, no characters, no portrait, no text`.
4. **Stage 2:** **Stability AI** or **Flux.1** (economical); **GPT Image** for hero frames.
   Enable **Style lock** → **Landscape / scene** preset is auto-selected.
5. Template uses **16:9** — change aspect in Builder before apply if you need square NFTs.

#### Manual matrix (50+)

**Scene / Location** × **Mood / Lighting** — avoid PFP categories. On-chain traits: `Scene`,
`Mood / Lighting`.

#### Cheat sheet

```text
25 landscapes:
  Atmospheric Worlds → Style Bible (no characters) → Flux/Stability Pilot
  → Curator → Export
```

### 4.1.4 Event / POAP / commemorative badges

Commemorative **badges** for conferences, DAO events, community seasons — **25** variants
(5 tiers × 5 visual styles). Event names and dates belong in **metadata**, not prompts
(AI renders text poorly).

#### Template 🎫 Event Badge Series

1. **Sidebar → 🎫 Event Badge Series → Apply**.
2. **Idea** — event name in **English without the year**:
   prefer `neon summit commemorative badge, no readable text` over literal dates in the prompt.
3. **Style Bible** — `no random text, no dates, no watermark`.
4. **Stage 2:** **GPT Image**; **Style lock** → **Event badge / medallion** preset (`event_badge`).
5. In **export**, set `name`: `Your Event #12`, English `description`, attributes `Tier`, `Visual Style`.

#### Tier and rarity

Matrix tiers are uniform by default; for a rare "Founder" tier use Classic weights or a
single line in **Custom text**.

#### Cheat sheet

```text
25 event badges:
  Event Badge Series → edit idea (EN, no dates in prompt) → GPT Image Pilot
  → Curator ≥4★ → Export → fill collection name in metadata
```

### 4.1.5 Fine art / 1/1 / ink wash

For **gallery-style pieces** without a trait matrix — `archetype: fine_art`. One prompt per
token; Style lock uses the **fine_art** suffix (cohesive art piece, no collage clutter).

#### When to use

| Goal | Template | Supply |
|---|---|---|
| Single premium hero image | **🎨 1/1 Fine Art** | 1 |
| Mini monochrome series | **🖋️ Sumi-e Ink Studies** | 25 (5 motifs × 5 moods) |
| Custom fine-art line | Manual style **Ink Wash / Sumi-e** or **Oil Painting / Classical** | any |

#### Recipe — 1/1 Fine Art

1. **Sidebar → 🎨 1/1 Fine Art → Apply** (or Pipeline → Stage 1 → **Single**).
2. Edit **idea** in English — one subject, one mood; avoid cramming several scenes in one line.
3. **Style Bible** — lock style, lighting, aspect ratio (template defaults to **16:9** for oil/classical).
4. **Stage 2:** **GPT Image** or **Flux Final** for hero quality; enable **Style lock** → **fine_art**.
5. Curator → export as a single-token drop.

#### Recipe — 25 ink-wash studies (Sumi-e)

1. **Sidebar → 🖋️ Sumi-e Ink Studies → Apply**.
2. Matrix axes: **Form / Silhouette** × **Background / Field** — no characters required.
3. **Stability AI** or **Flux** (painterly); negative bans text and photographic noise.
4. Export with EN trait names `Form`, `Background`.

#### Cheat sheet

```text
1/1 gallery piece:
  1/1 Fine Art → edit idea → Style Bible → GPT Image Final → Export

25 zen ink studies:
  Sumi-e Ink Studies → Pilot → Stability/Flux → Curator → Export
```

### 4.1.6 How styles work in w3ir (full guide)

The app ships **29 curated art-style presets**. Each preset is a **prompt fragment** (the full
English string in the dropdown) plus a **short UI description** — descriptions are **not** sent
to the image API unless you also pick that style in the builder.

#### Where styles appear

| Place | What it does |
|---|---|
| **Pipeline → Stage 1** | **Style** dropdown on matrix/single; caption under the box explains the preset |
| **Pipeline → Style Bible** | Locks one style for the **whole** drop (recommended for collections) |
| **Classic → ① Builder** | Same dropdown + **📖 Style catalog** expander (all 29 with descriptions) |
| **Sidebar → Apply template** | Sets style + traits + Bible from a collection recipe |
| **Stage 1 → Specific group** | **Multiselect** styles — one subject rendered in several looks |

#### Three ways to set a style

1. **Fastest — template:** sidebar template → **Apply** → style, traits, Bible, Style lock suffix and archetype negative are prefilled.
2. **Flexible — Style Bible:** pick any of the 29 presets in **Style** field → **💾 Save bible** → every prompt in the drop shares that look.
3. **Exploratory — Specific group:** one **idea** × **3–10 styles** from the multiselect → good for comparing looks before committing to a 50+ run.

**Rule of thumb:** uniform PFP / brand / event drops → **one** style via Bible or template.
Style exploration / mood boards → **Specific group** or Pilot with 2–3 styles.

#### Style lock suffix presets (Stage 2)

When **Style lock** is on, the app appends a consistency suffix (+ your Style Bible). After
**Apply template**, the suffix is chosen from the template **archetype**:

| Archetype | Style lock preset | Typical drop |
|---|---|---|
| `pfp` | **Portrait / PFP** | avatars, characters |
| `abstract_geometric` | **Geometric** | no faces, clean shapes |
| `landscape` | **Landscape / scene** | vistas, no people |
| `brand_icon` | **Brand mark** | logos, mascots, flat icons |
| `event_badge` | **Event badge / medallion** | tiers, enamel, seals |
| `fine_art` | **Fine art** | 1/1, gallery pieces |

Manual builds without a template: the app guesses the preset from keywords in your style/idea text
(e.g. `glitch` → geometric, `sumi-e` → fine_art, `medallion` → event_badge).

#### Engine hints by style family

These are **recommendations**, not hard rules — always run **Pilot** first.

| Style family | Examples | Often better engine | Why |
|---|---|---|---|
| **Flat / vector / icon** | 2D Vector, Flat UI, Minimalist Line Art | **GPT Image** | crisp edges, simple shapes |
| **Logo / badge / text-adjacent** | Brand, Event badge, Art Deco medallion | **GPT Image** | fewer random glyphs |
| **Painterly / illustration** | Watercolor, Comic, Anime, Clay, Oil, Sumi-e | **Stability AI** | stylized brush and line |
| **Photoreal / chrome / 3D** | Photorealistic Portrait, 3D Premium, Holographic Chrome | **Flux** or **GPT Image Final** | skin, metal, depth |
| **Neon / synth / cyber** | Cyberpunk, Synthwave, Dark Fantasy | **Flux** (pilot) → **Stability** or **GPT** for finals | strong mood, economical tests |
| **Pixel / voxel / low poly** | Pixel Art, Low Poly / Voxel | **Stability AI** | consistent stylization |
| **Abstract / glitch** | Generative Abstract, Glitch Art | **Stability AI** or **Flux** | shapes and color fields |
| **Landscape / matte** | Matte Painting, Retro Futurism Poster | **Flux** or **Stability** | atmosphere, wide shots |
| **Chibi / kawaii / toy** | Chibi, Vinyl Toy, Anime | **Stability AI** | cute proportions, bold outlines |

The **idea** field also nudges the default engine suggestion (e.g. `logo` → GPT, `watercolor` → Stability, `cinematic portrait` → Flux).

#### Mini-templates (25 NFT) — quick map

| Template | Style preset | Archetype |
|---|---|---|
| 🔷 Abstract Geometry Series | Generative Abstract | `abstract_geometric` |
| 📺 Glitch Geometry | Glitch Art / Datamosh | `abstract_geometric` |
| 🌄 Atmospheric Worlds | Matte Painting Landscape | `landscape` |
| 🛸 Retro Poster Series | Retro Futurism Poster | `landscape` |
| 🏷️ Brand Icon System | Flat UI / App Icon | `brand_icon` |
| ✒️ Line Art Monograms | Minimalist Line Art | `brand_icon` |
| 🎫 Event Badge Series | Badge / Medallion Engraving | `event_badge` |
| 🏛️ Art Deco Medallions | Art Deco / Art Nouveau | `event_badge` |
| 🖋️ Sumi-e Ink Studies | Ink Wash / Sumi-e | `fine_art` |
| 🍡 Chibi Champs | Chibi / SD Kawaii | `pfp` |
| 🧸 Vinyl Toy Squad | Toy Vinyl Collectible | `pfp` |
| ✨ Chrome Fashion Icons | Holographic Chrome Fashion | `pfp` |
| 🌅 Synthwave Retro | Synthwave / Vaporwave | `pfp` (large 5k+ label) |

Large PFP templates (BAYC, Flat Vector Mascots, Cyberpunk, Anime, Pixel 10k, Voxel, Watercolor, Comic, Clay, Photorealistic, Luxury Gold, Nature Spirits, etc.) each ship with their own style — open the template label in the sidebar to see which preset it uses.

**🟡 Flat Vector Mascots** is the most predictable template for an even drop: six object slots
(headwear, eyewear, outfit, mouth accessory, background with pattern, expression) and a strict
series frame. Use it as the reference when building your **own** trait set — see **§ 4.1.0**.

#### Specific group — one hero, many styles

Use when you want **stylistic** variations, not trait swaps:

1. Stage 1 → **Specific group**.
2. **Idea** — one English subject (`neon owl alchemist`).
3. **Styles** — multiselect 3–8 presets (e.g. Cyberpunk + Watercolor + Pixel Art + Chibi).
4. **Rich prompts** → Pilot on Stage 2 → pick the winning style → restart the real drop in **Matrix** or with a **template** in that style.

Not ideal for a uniform 10k PFP — great for **mood boards** and client previews.

### 4.1.7 Catalog — all 29 style presets

Open **📖 Style catalog** under the style dropdown (Builder or Pipeline Stage 1) for live
descriptions in your UI language. Reference table below.

#### PFP & character collections

| Style | UI label | Best for | Example template |
|---|---|---|---|
| 2D Vector Clean | 2D Vector Clean | Classic outlined PFP (BAYC-like) | BAYC-style PFP |
| Cyberpunk / Sci-Fi | Cyberpunk / Sci-Fi | Neon, chrome, sci-fi cities | Cyberpunk PFP |
| Anime / Kawaii / Manga | Anime / Kawaii | Expressive anime PFP | Anime PFP |
| Pixel Art / 8-Bit | Pixel Art / 8-Bit | Retro grid PFP | Pixel Art 10k |
| 3D Premium Render | 3D Premium Render | Glossy 3D PFP | Pixar-style 3D |
| Dark Fantasy / Dark Synth | Dark Fantasy | Moody gothic characters | Dark Souls PFP |
| Pop Art / Street Art | Pop Art / Street | Bold stencil/graffiti PFP | Pop Art Street PFP |
| Chibi / Super-deformed | Chibi / SD kawaii | Cute SD proportions | Chibi Champs |
| Photorealistic Cinematic Portrait | Photorealistic Portrait | Hyperreal studio PFP | Photorealistic PFP |
| Gothic Luxury / Baroque | Gothic Luxury | Gold, velvet, premium | Luxury Gold Portrait |
| Toy Vinyl Collectible | Vinyl toy | Designer toy gloss | Vinyl Toy Squad |
| Holographic Chrome Fashion | Chrome fashion | Runway, mirror materials | Chrome Fashion Icons |
| Synthwave / Vaporwave / Outrun | Synthwave | 80s neon grids, palms | Synthwave Retro |
| Afrofuturism / Solarpunk | Afrofuturism | Warm futurism + nature | Nature Spirits |
| Low Poly / Voxel 3D | Low Poly / Voxel | Blocky game-style 3D | Voxel Explorers |
| Watercolor Ink Illustration | Watercolor Ink | Soft painted PFP | Watercolor Dreams |
| Comic Book Western | Comic Book Western | Halftone, dynamic ink | Comic Heroes PFP |
| Clay Plasticine Stop-motion | Clay / plasticine | Rounded handmade 3D | Clay Creatures |
| Surrealism / Psychedelic | Surreal / psychedelic | Dreamlike distortions | Psychedelic Surreal |

#### Abstract, brand, landscape, fine art

| Style | UI label | Best for | Example template |
|---|---|---|---|
| Generative Abstract / Parametric | Generative Abstract | Algorithmic shapes, no character | Abstract Geometry Series |
| Glitch Art / Datamosh | Glitch / datamosh | RGB split, crypto-native abstract | Glitch Geometry |
| Minimalist Line Art | Minimalist Line Art | Sparse silhouettes, icon drops | *(manual — pair with Brand recipe § 4.1.2)* |
| Flat UI / App Icon Design | Flat UI / app icon | Vector brand marks | Brand Icon System |
| Badge / Medallion Engraving | Badge / medallion | Event tiers, embossed seals | Event Badge Series |
| Art Deco / Art Nouveau | Art Deco | 1920s luxury geometry | Art Deco Medallions |
| Matte Painting Cinematic Landscape | Matte painting | Epic environments, no people | Atmospheric Worlds |
| Retro Futurism Poster | Retro futurism poster | Vintage space-age posters | Retro Poster Series |
| Ink Wash / Sumi-e | Ink Wash / Sumi-e | Monochrome brush, zen | Sumi-e Ink Studies |
| Oil Painting / Classical Art | Oil / classical | Museum painterly 1/1 | 1/1 Fine Art |

#### Styles without a dedicated large template

**Minimalist Line Art**, **Oil Painting** (beyond 1/1), and **Surrealism** are available in the
dropdown for manual Bible/matrix work — pick the style, lock it in **Style Bible**, then build
your own trait axes or use **Custom text**.

#### Practical checklist before a styled drop

- [ ] Style chosen: template **or** Bible **or** intentional Specific-group test
- [ ] **Style lock** on for collections >5 images
- [ ] **Pilot** 5–10 frames with the recommended engine family (**§ 4.1.6**)
- [ ] Curator average ≥4★ before full queue
- [ ] Export attributes use EN trait names from the archetype

### 4.1.8 Beginner guides — every mini-drop (~25)

Step-by-step recipes for **first-time users**. All paths use **⛓️ Pipeline** and **sidebar → Apply template**.
Open **📖 Help** anytime; each recipe matches a template in **Collection templates** (~25 badge).

| Template | Supply | Matrix | Full recipe |
|---|---|---|---|
| 🎨 1/1 Fine Art | 1 | Single | **§ 4.1.5** |
| 🔷 Abstract Geometry Series | 25 | Form × Background | below |
| 📺 Glitch Geometry | 25 | Form × Field | below |
| 🌄 Atmospheric Worlds | 25 | Scene × Mood | **§ 4.1.3** + below |
| 🛸 Retro Poster Series | 25 | Scene × Palette | below |
| 🏷️ Brand Icon System | 25 | Layout × Background | **§ 4.1.2** + below |
| 🎫 Event Badge Series | 25 | Tier × Style | **§ 4.1.4** + below |
| 🏛️ Art Deco Medallions | 25 | Tier × Ornament | below |
| 🖋️ Sumi-e Ink Studies | 25 | Form × Background | **§ 4.1.5** + below |
| 🍡 Chibi Champs | 25 | Head × Outfit | below |
| 🧸 Vinyl Toy Squad | 25 | Character × Accessory | below |
| ✨ Chrome Fashion Icons | 25 | Pose × Accessory | below |
| 🌐 W3IR Showcase Demo | 25 | Head × Eyes (cyber PFP) | admin / staging only |

**Universal pipeline flow (all mini-drops):**

1. **💳 Credits** — Sign-In with wallet; ~**25–50 cr** for 25 Flux frames (+regenerates). **Creator $14.99 ≈ 400 cr** is enough.
2. **1️⃣ Text** — template applied → **Matrix** mode → 25 prompts auto-built → optional **Rich prompts** (1 cr each) → save queue.
3. **2️⃣ Images** — **Pilot 8–10** → curator ≥4★ → full batch → **Style lock** ON → approve all good frames → **Save and go to export**.
4. **3️⃣ Export** — preflight → ZIP (OpenSea / Thirdweb / Metaplex / W3IR) → optional IPFS → fill English `name` / `description`.

⏱ **~25–45 min** for 25 images (depends on regenerates).

---

#### 🔷 Abstract Geometry Series

**For whom:** crypto-native **abstract** drop — no faces, clean shapes, gallery/grid aesthetic.

| | |
|---|---|
| **Matrix** | **Form / Silhouette** × **Background / Field** (5×5 = 25) |
| **Style lock** | **Geometric** (`abstract_geometric`) |
| **Engine** | **Stability AI** or **Flux** (pilot first); GPT for extra polish on 2–3 heroes only |
| **Negative** | auto: no portrait, no character face |

**Steps:** Sidebar → **🔷 Abstract Geometry Series → Apply** → edit **idea** if needed (one abstract theme in EN) → Stage 1 confirms **25** prompts → Pilot → full run → export.

**Avoid:** PFP trait labels; cramming text into prompts.

```text
Abstract 25: Apply template → Matrix 25 → Flux Pilot 10 → Curator ≥4★ → Export ZIP
```

---

#### 📺 Glitch Geometry

**For whom:** **datamosh / RGB-split** abstract — crypto-art grids, no characters.

| | |
|---|---|
| **Matrix** | **Form / Silhouette** × **Background / Field** (glitch fields) |
| **Style lock** | **Geometric** |
| **Engine** | **Stability AI** or **Flux** — glitch reads better with consistent stylization |

**Steps:** Same as Abstract, but keep **idea** short (`corrupted sacred geometry, RGB split`). Do not ask the model for readable text.

```text
Glitch 25: Glitch Geometry → Style Bible lock → Stability Pilot → Batch → Export
```

---

#### 🌄 Atmospheric Worlds (quick path)

**For whom:** **landscape / world** art — covers, 1/1 series, no people in frame.

| | |
|---|---|
| **Matrix** | **Scene / Location** × **Mood / Lighting** |
| **Aspect** | template default **16:9** — switch to 1:1 in sidebar before Apply if your marketplace needs squares |
| **Style lock** | **Landscape / scene** |
| **Engine** | **Flux** or **Stability**; GPT Image for 1–2 hero frames |

Full detail: **§ 4.1.3**. Welcome button: **🌄 Landscape 25**.

```text
Landscape 25: Atmospheric Worlds → Bible (no people) → Flux Pilot → Curator → Export
```

---

#### 🛸 Retro Poster Series

**For whom:** **vintage space-age posters** — retro-futurism without characters.

| | |
|---|---|
| **Matrix** | **Scene** × **Palette** (5×5) |
| **Style lock** | **Landscape / scene** |
| **Engine** | **Stability AI** or **Flux** — grainy print mood |

**Steps:** Apply template → refine **idea** (`1950s space tourism poster, no people`) → negative: `no characters, no portrait, no readable text` → Pilot → export.

```text
Retro posters 25: Retro Poster Series → 16:9 or 1:1 → Stability → Export
```

---

#### 🏷️ Brand Icon System (quick path)

**For whom:** **25 brand marks / app icons** — one identity, many backgrounds.

| | |
|---|---|
| **Matrix** | **Layout / Context** × **Background / Field** |
| **Style lock** | **Brand mark** |
| **Engine** | **GPT Image** recommended (crisp flat shapes) |

Replace **idea** with your mark in EN (`minimal owl mark, navy and gold, no text`). Full recipes: **§ 4.1.2**. Welcome: **🏷️ Brand icons 25**.

```text
Brand 25: Brand Icon System → edit idea (EN) → GPT Pilot → Curator → Export
```

---

#### 🎫 Event Badge Series (quick path)

**For whom:** **conference / DAO / season** commemorative badges — tiers as rarity.

| | |
|---|---|
| **Matrix** | **Tier** × **Visual style** |
| **Style lock** | **Event badge / medallion** |
| **Engine** | **GPT Image** |
| **Metadata** | event name and dates in **export**, not in prompts |

Full detail: **§ 4.1.4**. Welcome: **🎫 Event badge 25**.

```text
Event 25: Event Badge Series → idea (EN, no dates in prompt) → GPT → Export metadata
```

---

#### 🏛️ Art Deco Medallions

**For whom:** **premium event** or membership medals — gold lines, 1920s luxury geometry.

| | |
|---|---|
| **Matrix** | **Tier** × **Ornament pattern** |
| **Style lock** | **Event badge / medallion** |
| **Engine** | **GPT Image** — embossed metal reads best |

**Steps:** Apply → idea like `art deco gala medallion, geometric sunburst, no readable text` → Style Bible: `gold line art, no watermark` → Pilot → export with attributes `Tier`, `Ornament`.

```text
Art Deco 25: Art Deco Medallions → GPT Image → tier metadata in export
```

---

#### 🖋️ Sumi-e Ink Studies (quick path)

**For whom:** **monochrome ink** fine-art series — zen, no PFP.

| | |
|---|---|
| **Matrix** | **Form / Silhouette** × **Background / Field** |
| **Style lock** | **Fine art** |
| **Engine** | **Stability AI** (brush texture) |

Full detail: **§ 4.1.5**.

```text
Sumi-e 25: Sumi-e Ink Studies → Stability → Curator → Export (traits Form, Background)
```

---

#### 🍡 Chibi Champs

**For whom:** **kawaii / SD** PFP mini-drop — cute proportions, bold outlines.

| | |
|---|---|
| **Matrix** | **Head / Helmet** × **Outfit** (PFP axes) |
| **Style lock** | **Portrait / PFP** |
| **Engine** | **Stability AI** or **Flux** pilot → GPT finals on top 5 if budget allows |

**Steps:** Apply → one **idea** line for your squad theme (`chibi forest guardians`) → Pilot 10 → watch for **consistent face size** → regenerate outliers.

```text
Chibi 25: Chibi Champs → Flux Pilot → Style lock PFP → Curator → Export
```

---

#### 🧸 Vinyl Toy Squad

**For whom:** **designer vinyl toy** PFP — glossy plastic, collectible feel.

| | |
|---|---|
| **Matrix** | **Character variant** × **Accessory** |
| **Style lock** | **Portrait / PFP** |
| **Engine** | **Stability AI** — toy material and studio light |

**Steps:** Apply → idea `designer vinyl toy character, studio product shot` → keep backgrounds simple → Pilot → full run.

```text
Vinyl 25: Vinyl Toy Squad → Stability → Curator ≥4★ → Export
```

---

#### ✨ Chrome Fashion Icons

**For whom:** **editorial fashion** PFP — chrome, runway, holographic materials.

| | |
|---|---|
| **Matrix** | **Pose / Styling** × **Accessory** |
| **Style lock** | **Portrait / PFP** |
| **Engine** | **Flux** or **GPT Image Final** for metal/skin |

**Steps:** Apply → idea in EN (`holographic chrome fashion portrait`) → avoid clutter in Style Bible → Pilot → export.

```text
Chrome 25: Chrome Fashion Icons → Flux/GPT → Curator → Export
```

---

#### 🎨 1/1 Fine Art (single token)

Not a 25-drop — use Welcome **🚀 1 NFT** or template **🎨 1/1 Fine Art**. Full recipe: **§ 4.1.5** and Welcome expander **📋 Detailed guide**.

---

#### 🌐 W3IR Showcase Demo

**Staging / admin** walkthrough: 25 cyber PFP (5×5). Public users should pick **🔷 Abstract Geometry** or another mini-template above.

---

**More mini-drops:** sidebar **Collection templates** filter by **~25** badge. Style reference: **§ 4.1.6–4.1.7**. Large PFP collections (1k–10k) → **§ 5.1** Classic path.

### 4.2 Stage 2️⃣ — Images

**Before you start:** connect a wallet at **💳 Credits** and make sure your balance > 0.

| Engine | Credits per image | Note |
|---|---|---|
| **Flux.1** | 1 | fast, economical |
| **Stability AI** | 1 | consistent style |
| **GPT Image** | 4 | premium OpenAI quality |

- Pick a **size** (square / portrait / landscape).
- The queue runs one image at a time with a progress bar; if one prompt fails, the rest continue.
- Credits are reserved at the start of each generation and are **automatically refunded** if it fails — you only pay for successful images.

How to choose an engine:

| Task | Often better |
|---|---|
| Logo, typography, clear object | **GPT Image** |
| Artistic style, illustration, watercolor/concept art | **Stability AI** |
| Fast inexpensive pilot, many variants | **Flux.1** |
| Final 1/1 or hero images | **GPT Image** or Final tier |

Available modes at stage 2:

- **Batch** — generate the selected number of prompts.
- **Pilot** — a small test batch before a large run.
- **A/B** — one prompt through two engines to compare style.
- **Draft / Final / Hybrid** — cheap drafts, more expensive final frames, or a mix.
- **Reproducibility seed** — fixed seed for Stability/Flux to reproduce the collection.

**Curator panel** (after the queue):

- A **1–5** star rating per image; **⭐ QA → ★** fills stars from Auto-QA for frames not yet manually rated.
- Filters: min rating, Rarity Score, tier, text in traits.
- Mark **"Approve"** only on the good ones.
- **Batch:** for large queues — **"Continue from #N"** appends without overwriting finished frames; **"Clear batch"** resets batch progress.
- **✅ Save and go to export** — adds approved to the queue and opens **Stage 3** right away (for 1/1 — a simplified curator with the same button).

Each image has a **prompt attached** (Prompt-Lock) — it will go into the NFT metadata.

Before a large queue, check that:

- the balance covers at least the first 5–10 images;
- prompts are not duplicated and do not contain extra platform tags;
- Style Bible or Style lock is enabled if the collection should be visually consistent;
- you understand that **Final** costs more than Draft.

### 4.3 Stage 💳 — Credits

**If you signed in to the app with a wallet — you're already connected here** (the same wallet, no second signature); your balance shows right away. The buttons below are only for manually connecting or switching wallets.

| Action | Description |
|---|---|
| **Connect MetaMask** | one-click Sign-In (EVM, `personal_sign` on Base) |
| **Connect Phantom** | one-click Sign-In (Solana, `signMessage`) |
| **Balance** | how many generations are left |
| **Helio packages** | payment in **USDC on the Base network** |
| **Check payment** | if credits don't appear right after paying |

**If the MetaMask / Phantom buttons don't appear** — open **"Manual connection"**: paste your address, **"Get message"**, sign it in your wallet, paste the signature.

**Image generation** is available only after **ownership is confirmed by a signature** (entering someone else's address is not enough).

**The sign-in message is one-time and valid for ~10 minutes** (replay protection). If you took too long to sign, get a fresh message and sign again.

**Welcome credits:** a new **EVM** wallet can get **5 credits** if it holds a small amount of ETH on Base (protection against mass fake wallets). **Solana** — 5 credits after a Phantom signature (no SOL balance check).

**Packages (reference):**

| Package | Price | Credits |
|---|---|---|
| 🟢 Start | $4.99 | 100 |
| 🟡 Creator | $14.99 | 400 |
| 🔵 Pro | $29.99 | 1000 |

**Example:** 25 NFTs on Flux = 25 credits; on GPT Image = 100 credits.

Important credit rules:

- credits are spent **for generation**, not for viewing or export;
- failed generation refunds credits automatically;
- if engine cascade is enabled and a provider fails, the app may try another ready engine and reconcile the cost against the engine that actually produced the result;
- welcome-only wallets: up to **10 generations/min** (batch runs in waves); after top-up (Helio) or **grant** — no such cap;
- free credits may have a daily anti-abuse cap (if enabled on the server); paid packages and grants are exempt;
- administrator access to the admin tab **does not** mean free generations.

Choose a package based on supply and engine: 100 Flux/Stability images need roughly 100 credits, 100 GPT Image results need roughly 400 credits, and Final quality should be planned with a buffer.

### 4.4 Stage 3️⃣ — Export

**Input:** approved works from stage 2 (the queue fills **automatically** after "Save and go to export"; the **"📥 Add approved work to queue"** button is a manual refresh, e.g. after new approvals) **or** uploading your own JPG/PNG.

The app **does not mint by itself** — it prepares the content (images + metadata) in the format of the chosen platform, and **you mint** wherever it's convenient. In-app minting stays optional (below, under "Advanced").

**Exporting the bundle (main action)**

Choose a **platform/format** and build the package:

| Format | Layout | Where to take it |
|---|---|---|
| **OpenSea / ERC-721** | `images/` + `metadata/<n>.json` + `collection.json` (1-indexed) | OpenSea Studio drop, any EVM service |
| **Metaplex** | `assets/<i>.png` + `<i>.json` (0-indexed) | Sugar CLI |
| **Candy Machine** | `assets/` + `config.json` + guards (+ `allowlist.json`) | Sugar CLI — folder ready for `sugar deploy` |
| **thirdweb Batch Upload** | `images/` + `metadata.csv` | thirdweb dashboard → Batch Upload |
| **Generic ZIP** | universal `images/` + `metadata/` + `collection.json` | anywhere |
| **W3IR Platform** | `.w3ir-nft.zip` with manifest/mint-state/assets | direct import into the W3IR mint platform |

Two delivery options (for OpenSea / thirdweb / Metaplex / Generic):

- **🗜️ ZIP** — download the archive locally. At the root, **`README.txt`** is a step-by-step mint guide in the **same language as the UI** during the build (🇺🇦 / 🇬🇧). On-chain metadata is always **English**.
- **📁 IPFS (Pinata)** — recommended for on-chain `baseURI`:
  1. Choose **who pins**: **W3IR Pinata (included)** or **My Pinata** (your JWT).
  2. **📤 Uploading images** → images folder CID.
  3. **🔧 Update JSON → 📌 Pin metadata** → each JSON `image` becomes `ipfs://<images CID>/<file>` → metadata CID.

  Output: `baseURI` `ipfs://<metadata CID>/` with a **copy button**; a **mint ZIP is built automatically** (`ipfs-manifest.json` + metadata with `ipfs://`).

  **Who pays for IPFS (Pinata):**

  | Scenario | Who pays | Credits | Access |
  |---|---|---|---|
  | **W3IR Pinata (included)** — platform shared key | **W3IR** (bonus) | not charged | only after **top-up** (Helio) or **grant** |
  | **My Pinata** — your JWT in the export field | **you** — [pinata.cloud](https://pinata.cloud) | not charged | all wallets |
  | **ZIP only**, no in-app IPFS | no in-app charge | not charged | all |

  If no shared key is configured on the server — **My Pinata** or **ZIP** only. JWT is entered hidden, in the session, **not stored**. There is no separate IPFS surcharge in credit packages — credits are spent **only on generation** (see § 4.3).

  **W3IR Platform** and **Candy Machine** — separate IPFS in Export Center is not needed (import `.w3ir-nft.zip` or `sugar deploy` uploads assets itself).

The metadata includes: name, description, image, **attributes** in English, **Generation Prompt** (the locked prompt), **Collection ID** and provenance (rarity, hash).

What the ZIP contains:

- `images/` or `assets/` — image files;
- JSON metadata or `metadata.csv`, depending on the platform;
- `README.txt` — mint guide in the UI language; `collection.json` — summary (where applicable);
- after IPFS — also `ipfs-manifest.json` with baseURI and CIDs;
- provenance fields: engine, prompt hash, rarity rank/tier, collection id;
- `Made with w3ir.io` attribution, unless disabled for the plan/operator.

Before export, check that:

- every token has an image;
- collection name, description, symbol and creator are filled in English;
- only works that really go into the drop are approved;
- for Metaplex / Candy Machine, symbol is short, royalties are expected, creator is the correct Solana address;
- for IPFS: pick a Pinata mode (**W3IR** — if topped up/grant; otherwise **My Pinata** JWT or ZIP only).

#### 4.4.1 NFT Quality Checklist (AI advisor)

In Export Center — expander **🤖 NFT Quality Checklist** (above ZIP/IPFS). **Does not block export** — only a **0–100** score and pre-mint advice for OpenSea, Magic Eden, Blur, etc.

| Step | Action | Cost |
|---|---|---|
| 1 | Tick **self-check** (Discord, Telegram, X, waitlist, utility, reveal, rights) | free |
| 2 | **▶️ Run checklist** — visual, metadata, technical, economics | free |
| 3 | **✨ AI tips** (1 cr) or **🔬 AI deep dive** (5 cr) — thumbnail + style consistency | optional |
| 4 | Download `quality-report.json` / `.md` for your team | free |

**Scale:** 90–100 ready to publish · 75–89 minor fixes · 60–74 significant work · &lt;60 high drop risk.

**Checked automatically:** resolution and file size, descriptions (100–600 chars), hashtags, traits/rarity, JSON metadata, IPFS probe, royalty %, supply, platform hints.

**You confirm manually:** social channels, utility, reveal, content rights, platform policy.

The **📖 Help: this step** button in the expander opens this section.

#### 4.4.2 Competitive Drop Recipe

The optimal path to a marketplace-ready collection — without extra engines or preset sprawl:

| # | Step | Where in the app |
|---|------|------------------|
| 1 | **Archetype template** + Style Bible | Sidebar → template → Stage 1 |
| 2 | **Pilot 10** → rating → **engine winner** | Stage 2 → Pilot → Curator |
| 3 | **Full batch** + bulk **≥4★** | Stage 2 → «Approve all ≥ N★» |
| 4 | **QC ≥75** (free checklist) | Export Center → NFT Quality Checklist |
| 5 | **Upscale 2048** + **IPFS** (Pinata) | Export Center → upscale checkbox → IPFS |
| 6 | **Export** + publish **`/c/<slug>`** | Platform ZIP + Share |

**Naming:** in Export Center — **✏️ Collection naming (EN)** expander — `Brand #N` names, EN description and hashtags in one click.

**Targets:** median time to export **< 15 min**, save without regenerate **≥ 70%**, QC score **≥ 75** (advisory).

Choosing a format:

| Need | Format |
|---|---|
| Easiest thirdweb upload | **thirdweb Batch Upload** |
| EVM/OpenSea-style metadata | **OpenSea / ERC-721** |
| Solana Sugar (basic assets/) | **Metaplex** |
| Solana drop with price, dates, whitelist | **Candy Machine** |
| Handoff to a developer or another tool | **Generic ZIP** |
| Import into the W3IR mint platform | **W3IR Platform** |

**⚙️ Advanced — minting in the app (optional)**

If you still want to mint right here:

| Engine | Network | What you provide |
|---|---|---|
| **Thirdweb** | Base (EVM) | the NFT Collection contract address, recipient wallet, minter key (entered in the session, not stored), ETH for gas |
| **Crossmint** | Base or Solana | API Key and Collection ID (entered in the session); for tests, enable **Staging** |

- First pack into IPFS (Token URI), then mint. For a batch on Base — **Batch mint** (one transaction for the whole queue, cheaper gas).
- **Reveal mode** (optional): metadata first shows a placeholder image; the real one comes after the drop.
- After a successful mint, temporary files on the server are cleaned up — the content is already in IPFS.

**Security:** never share your seed phrase; use a separate wallet with a minimal balance for minting.

### 🎯 Generation quality controls

To keep the whole collection consistent and avoid burning credits on weak frames:

- **🎨 Style Bible (Stage 1):** lock the collection's style, lighting, camera and background rule (you can "fill from a template"). Saved per your wallet.
- **🎨 Style lock (Stage 2):** appends a consistency suffix + your Style Bible to every prompt and (optionally) a **negative prompt** (Stability uses it natively). Suffix preset follows collection **archetype** — see **§ 4.1.6**.
- **✨ LLM polish (Stage 1):** rewrites raw matrix prompts into style-consistent ones + negative, preserving traits. **1 credit per ~15 prompts**; Light/Full modes.
- **🧪 Pilot (Stage 2):** generate a small pilot batch before the full queue. The Curator panel shows the **average rating**, the **winning engine**, and an **"Approve all ≥ N★"** button.
- **Quality tier (Stage 2):** **Draft** — cheap draft; **Final** — higher quality at higher cost (gpt-image high, Flux flux-dev); **Hybrid** — first N as Final, the rest as Draft.
- **🎲 Reproducibility (seed):** a fixed base seed reproduces the same collection (for Stability/Flux; OpenAI ignores seed).
- **Incompatible traits (Stage 1):** define pairs that must not co-occur (e.g. `golden crown | viking helmet`) — such combinations are filtered out before generation.
- **Prompt lint:** the Stage 1 preview flags empty, too short/long and duplicate prompts.
- **🔬 Detailed Image-to-Prompt:** a more accurate image breakdown with the gpt-4o model.

---

## 5. Collection — classic path (tabs ①–⑤)

A brief overview of the extra tabs if the **🏭 Collection** mode is selected.

### ① Builder

One detailed prompt to validate a concept: character, style, lighting, background, MJ tags. Buttons **🎲 / 💡 / 🎰** — random variants.

Open **📖 Style catalog** (expander under the style dropdown) to browse all **29 presets** with descriptions — **§ 4.1.7**. Use the Builder as a "lab" for the collection tone: first find a good style, then multiply it in Batch or Pipeline. If the result describes the future drop well, save the project in the sidebar.

### ② Traits

#### Recommended approach (product default)

Do not treat it as “template **or** manual entry” — use this **cascade**:

| Step | Who | Where in the UI |
|---|---|---|
| 1. Collection scaffold | **Template** | Sidebar → **📋 Collection templates** → **✅ Apply** |
| 2. Trait names | **Template** (auto) | Classic **② Traits** *or* Pipeline **Stage 1 → Matrix** |
| 3. Rarity | **You** | **② Traits**: `name \| weight` or **🎲 Rarity sliders** |
| 4. Fine-tuning | **You** (optional) | Add/remove lines in category fields |

**Templates fill names only** (no weights). After **Apply**, review the lists and set weights before Batch or Collection.

| Mode | Where to edit trait layers | When |
|---|---|---|
| **⛓️ Pipeline** (default) | **Stage 1 → Matrix**; prompts already queued | 25 mini-drops, abstract, brand |
| **Classic (Advanced)** | **② Traits** → **③ Batch** → **④ Collection** | 100–10,000 NFT, checkpoints, weights |

**Manual from scratch** (no template) — for fully custom collections: fill all six categories yourself or paste lists from another project. Template and manual are **not mutually exclusive**: re-apply a template from the sidebar to refresh trait fields (re-check weights afterward).

#### Format and rules

Six categories (head, eyes, clothing…). Format with a rarity weight:

```
golden crown | 1
baseball cap | 20
```

A lower weight = a rarer trait.

Recommendations:

- do not duplicate the same trait with slightly different wording (`gold crown` and `golden crown`);
- for rare traits use weight 1–3, for common traits 20–50;
- do not create mutually exclusive traits in one category if they should be independent;
- use English names if you want clean marketplace attributes without translation.

### ③ Batch

10–200 prompts at once, **rarity score**, CSV/JSON export, ERC-721 / Metaplex metadata. At the bottom — **"→ To Pipeline"** to continue.

Batch is useful for checking trait distribution before spending on images. If you see too many identical combinations or weak prompt lines, go back to Traits and adjust the weights.

### ④ Collection

Up to **10,000** tokens with **checkpoints** (you can interrupt and resume). Then images, IPFS, ZIP. There's also a bridge to the pipeline.

For large collections, work in blocks:

1. Generate a small batch and check quality.
2. Run the full collection with checkpoints.
3. Review CSV/metadata before image generation.
4. Generate images with a budget or move the best set into the pipeline.

A checkpoint saves the run state, so closing the browser does not mean losing already generated prompts. For supply **100–10,000**, pausing across days and credits — see **§ 5.1** below.

### 5.1 Large collections (100–10,000 NFT): approaches, pause, credits

On **ai.w3ir.io**, a large generative drop (e.g. **1000 NFT**) is usually a **hybrid**: **Classic** first (prompts + rarity + checkpoints), then **Pipeline** (images, curator, export). There is no dedicated **Pause** button — stopping means closing the tab or waiting for the current wave to finish; progress is saved on the server.

#### Which approach to pick by supply

| Supply | Collection type | Recommended path | Why |
|---|---|---|---|
| **25** | PFP or abstract | **Pipeline** → matrix or template | Fast; Pilot + curator |
| **50–100** | PFP, many traits | **Pipeline** or Classic **Batch** → bridge | Still manageable without checkpoints |
| **100–10,000** | PFP, 6 trait categories | **Classic → Collection** → **"→ To Pipeline"** | Checkpoints, rarity weights, resume |
| **100–10,000** | Abstract / geometry | Same Classic → Pipeline, but **2–3 axes** (form × background × palette), not 6 PFP layers | AI holds composition better |
| **1/1** | Fine art | **Pipeline → Single** | Classic Collection not needed |

**Not recommended** for 1000 NFT: **Pipeline matrix only** without Classic — no checkpoint for a thousand prompts; combinatorics get unwieldy fast.

#### Golden path for ~1000 NFT (PFP)

```text
Welcome → "⚙️ Advanced" (Classic)
  → Template + Traits (rarity weights; combos ≥ supply)
  → Batch: test 10–20 prompts
  → Collection: 1000 prompts (checkpoint)
  → "→ To Pipeline"
  → Stage 2: Pilot 10–20 → engine winner → image waves
  → Curator: bulk ≥4★ → Export
```

Before the full run — **dry-run** 3–5 images in the Pipeline (see § 1).

#### Two phases — different credit logic

| Phase | Where | Charging | If credits run out |
|---|---|---|---|
| **Prompts** | Classic → **Collection** | **1 cr per prompt**, reserve for the **full remaining run** on start or **Resume** | Start/resume **won't begin** if balance < required (e.g. 1000 from scratch needs ≥1000 cr) |
| **Images** | **Pipeline** → Stage 2 | **Per image** (Flux draft ≈1 cr; gpt-image costs more) | Finished frames **stay saved**; the rest get "credits exhausted" **without charge** |
| **API failure** | Anywhere | — | Credits for failed generations are **refunded** automatically |

Credits on your balance **do not expire** — top up tomorrow and continue. Credits spent on **successful** generations are **non-refundable** (see [refund policy](https://w3ir.io/legal/en)).

**Budget guide for 1000 NFT (ai.w3ir.io, Flux draft):** ~1000 cr prompts + ~1000 cr images + regenerate headroom ≈ **2200–2500 cr**. The **Pro (1000 cr)** package usually **isn't enough** for the full cycle — plan several top-ups or **work in waves**.

#### Pause and continue "until tomorrow"

**Prompts (Collection)**

- Checkpoint on disk updates after **each block** (~10 prompts).
- You can close the browser — finished prompts remain.
- Next day: same wallet → Classic → **Collection** → pick run → **"Resume"**.
- Resume charges only the **remainder** (e.g. 600 of 1000).

**Images (Pipeline)**

- **📂 Project** autosave: prompts, PNGs, curator ratings, Style Bible.
- Welcome → **"Continue last project"** or **My projects**.
- At Stage 2 set **Limit** to what your balance allows now (e.g. 200) and run another wave.
- **Don't** blindly re-run the full 1000 on the same prompts — you may duplicate frames. Prefer waves of **100–200** or keep approved items in the curator queue.

**Rate limit:** ~**10 successful generations/minute** per wallet. Even with a large balance, 1000 frames take **many minutes** — plan several sessions.

#### Multi-day workflow variants

| Variant | When it fits | How |
|---|---|---|
| **A. Prompt waves** | Balance < supply | Collection **Resume** in chunks of 200–300 prompts/day |
| **B. Image waves** | Prompts already 1000/1000 | Pipeline Stage 2, **Limit** = balance ÷ cost_per_image |
| **C. Metadata first** | Time but few cr for images | Finish Collection at 1000 → review CSV → images later |
| **D. Quick preview (Classic)** | Test 1–4 frames before pipeline | **⑤ Quick preview**: OpenAI key + **4 cr/frame** on ai.w3ir.io (separate from OpenAI USD). No key — Pipeline |

#### What is preserved and what does not happen

| Situation | Reality |
|---|---|
| Closed the tab mid-run | Prompts in checkpoint; images in **📂 Project** |
| Credits ran out | Already generated work **remains**; top up → Resume / Run with Limit |
| "Pause" button | **None** — only saved progress |
| Auto-continue after Helio | **None** — you must Resume or Run again |

**Abstract / geometry:** **25–100** NFTs — **Pipeline** + *Abstract Geometry Series* template in the sidebar; **500+** — **Classic → Collection** with **2–3 trait axes** (shape × background × palette), then **"→ To Pipeline"**. Summary table — in **§ 2**.

### ⑤ Quick preview

Test **1–4 images** for a single prompt via **gpt-image-1**. Separate from the pipeline and from bulk image generation in **④ Collection**.

**Required on ai.w3ir.io:**

1. Connected **wallet** (Sign-In).
2. **OpenAI API key** in sidebar → AI settings.
3. **4 credits per frame** on the platform (separate from USD charged by OpenAI on your account).

**Not a mint-ready drop:** no curator, Prompt-Lock or export gate. PNGs are drafts in `data/previews/` — download them if you need to keep them.

**When to use what:**

| Situation | Where to go |
|---|---|
| Quickly test one prompt | **⑤ Quick preview** |
| Bulk PNGs for a run (USD budget) | **④ Collection** → images |
| Finished drop with curator and export | **⛓️ Pipeline → 2️⃣** or **"→ To Pipeline"** |
| No OpenAI key | **⛓️ Pipeline → 2️⃣** (Flux/Stability for credits) |

### 📜 History

The last 50 single generations from the Builder; search by text.

History is not a full project archive. For important settings use **Projects** in the sidebar, and for a finished drop use ZIP/IPFS export.

---

## 6. Metadata and NFT language

What ends up on the marketplace:

```json
{
  "name": "My Collection #7",
  "description": "English description for OpenSea",
  "image": "ipfs://…",
  "attributes": [
    { "trait_type": "Head", "value": "golden crown" }
  ]
}
```

- Fill in the **collection name** and **description** on the export forms in **English**.
- Traits in the UI may be in Ukrainian; in batch/pipeline the LLM often translates attributes into EN.
- In the pipeline the prompt is stored as a **Generation Prompt** attribute.

Practical NFT standard:

- `name` is short and stable: `Collection Name #1`, `Collection Name #2`;
- `description` explains the set but does not include private notes;
- `attributes` use consistent `trait_type` values across the whole collection;
- `image` is either a local file in the ZIP or `ipfs://...` after IPFS publishing;
- royalties/creator should be the values you will really use when minting.

What provenance means in the bundle:

| Field | Why it exists |
|---|---|
| **Generation Prompt** | records the prompt used to create the art |
| **Prompt Hash** | helps verify the prompt was not changed |
| **Engine / Model Version** | shows which engine created the image |
| **Rarity Rank / Tier** | helps sort and present the collection |
| **Collection ID** | links tokens from one drop |

Do not put seed phrases, private keys, buyer emails or internal notes into metadata — those fields may become public.

---

## 7. FAQ

**I can't get into ai.w3ir.io**  
Sign-in is via your **wallet**: on the login screen click **Connect Wallet** and sign the message (gasless). Make sure **MetaMask** / **Coinbase** (EVM) or **Phantom** (Solana) is installed and the site is opened over **https://**. No wallet — use **"Request beta access"** or write to w3ir@pm.me.

**The login screen won't let me in / "signature verification failed"**  
Sign the message with the same wallet you connected, and don't delay — the sign-in message is one-time and short-lived. Refresh the page (F5) to get a fresh one and sign again.

**502 / the page won't load**  
The server is temporarily unavailable — try again later or write to the operator.

**MetaMask / Phantom won't connect**  
Make sure the site is opened over **https://** and the wallet extension is enabled. For EVM, select the **Base** network. If the buttons don't appear — use **"Manual connection"** at the 💳 Credits stage (address + signature).

**Paid via Helio — credits are there, but generation doesn't work**  
Generation requires a **wallet confirmed by signature**. If you signed in to the app with your wallet, it's already confirmed. Otherwise connect **the same** wallet at the 💳 Credits stage and sign the message.

**"Nonce expired" or the signature isn't accepted**  
The sign-in message is one-time and valid for ~10 min. Get a new message (the **"Get message"** button or reconnect MetaMask/Phantom) and sign it again.

**No 5 welcome credits**  
For **EVM**: the wallet needs a little ETH on Base, or it's not your first sign-in. For **Solana**: a Phantom signature is required on the first sign-in.

**The generate button is inactive**  
Connect a wallet **with a signature**, check your credit balance. At stage 2 you need prompts from stage 1.

**"Prompt rejected by content moderation"**  
The app filters disallowed requests (including sexualization of minors and sexual violence) **before** generation — no credits are charged. Reword the prompt. Ordinary creative prompts are not blocked.

**Image blocked by OpenAI output moderation (after generation started)**  
OpenAI may reject the **result** even when the prompt passed input checks. Click **Regenerate** and pick **Flux** or **Stability** — the app tries an automatic fallback when possible. Credits are reconciled for the engine that actually produced the image.

**Can I continue tomorrow where I left off?**  
Yes. **Pipeline:** **📂 Project** autosave (prompts, images, ratings, Style Bible) — **My projects** or Welcome "Continue last project". **Classic Collection:** prompt checkpoint on disk — **"Resume"** on a saved run (charges cr only for the remainder). Sign in with the **same wallet**. Details — **§ 5.1**.

**How do I make a 1000 NFT collection?**  
Recommended path: **Classic → Collection (1000 prompts)** → **"→ To Pipeline"** → images in **waves** (Limit at Stage 2). Don't start with a full Pipeline matrix at 1000. Full checklist, credit budget and multi-day variants — **§ 5.1**.

**Ran out of credits during the queue**  
**Images (Stage 2):** finished frames stay in **📂 Project**; top up → Run again with **Limit** (e.g. 200), not necessarily all 1000 at once. **Prompts (Collection):** if the run stopped — finished prompts are in the checkpoint; **Resume** charges for the remainder only. Start/resume **won't begin** if balance < remainder. API failures — automatic refund. Details — **§ 5.1**.

**How do I make 50 different characters in one style?**
See **§ 4.1.1** in this guide. In short: **Style Bible** → a list of 50 archetypes (**Matrix** 50×1, **10×5**, or **Custom text**) → **Rich prompts** → **Pilot** → generation at **Stage 2** → curator → export. For **50 variants of one hero**, a sidebar **template** (Cyberpunk / BAYC) + Limit 50 is easier.

**Where is the full list of art styles?**
**29 presets** in the **Style** dropdown on Pipeline Stage 1 and Classic Builder. Expand **📖 Style catalog** under the dropdown for descriptions. Full reference table — **§ 4.1.7**.

**Which style should I pick for my drop?**
Start from **§ 2** (path table) or a **sidebar template** that already matches your niche (PFP, abstract, landscape, event, fine art). If unsure, run **Specific group** with 3–5 styles on one idea, **Pilot**, then lock the winner in **Style Bible**. Engine families — **§ 4.1.6**.

**Can I mix several styles in one collection?**
For a **uniform** drop (PFP, brand, event) — **one** style via template or Style Bible. **Specific group** and manual matrix tricks can mix styles on purpose (e.g. seasonal variants) — expect less visual consistency; use curator strictly.

**Duplicate vs New project?**
**➕ New** — empty drop (default name: date and time). **📋 Duplicate** copies the current project (state + all PNGs) — good for A/B, but **uses disk space**. **🗑️ Delete** permanently removes a project from the server.

**How many projects can I have?**  
By default **no hard cap**; from 15 projects you'll see a sidebar warning. The operator may enable `WORKSPACE_MAX_PROJECTS_PER_WALLET` (free wallets) and `WORKSPACE_MAX_MB_PER_WALLET` (everyone). Paying users (Helio) are **exempt from the project count** cap; disk MB may still apply to all.

**Why do I see "$ spent this session" / credits?**  
In **classic mode** the sidebar shows estimated **USD** on **your** OpenAI/Anthropic account. On **ai.w3ir.io** that does **not** replace platform credits: LLM requests — **1 cr**, **⑤ Quick preview** — **4 cr/frame** (plus OpenAI USD). In **pipeline** mode the USD counter is hidden — you only see credits charged.

**Why does preview need both an OpenAI key and credits?**  
The **OpenAI key** pays the provider for gpt-image-1. **W3IR credits** on ai.w3ir.io unlock the generate button on the platform (anti-abuse). These are separate bills. No OpenAI key — use **Pipeline → 2️⃣** (Flux/Stability). Bulk images in **④ Collection** charge only the OpenAI USD budget, not platform credits.

**"Daily free-generation limit reached"**  
An anti-abuse daily cap applies to free credits. Top up on **💳 Credits** (paying users are unlimited) or try again next day (resets at 00:00 UTC).

**Hint "the … engine fits this idea well"**  
A suggestion based on your idea text (logo/typography → gpt-image-1; art/watercolor → Stability; photo/cinematic → Flux). Optional — pick any available engine.

**Paid via Helio — no credits**  
Click **"Check payment"**; wait 1–2 min. Payment is only **USDC on Base**.

**Who pays for Pinata hosting?**  
IPFS export **does not spend credits**. On **ai.w3ir.io**, **W3IR Pinata (included)** is a bonus for wallets with a **top-up** (Helio) or **grant** — pins and storage on the platform account. Welcome-only users — **My Pinata** (your JWT) or **ZIP**. Details — table in **§ 4.4**.

**IPFS upload fails or "Pinata limit"**  
Pinata has a rate limit — the app **automatically retries with a pause**. If the error persists, wait a minute and retry, choose **My Pinata** and enter your own JWT, or build **ZIP** and upload files yourself. For large collections the upload takes longer — that's normal.

**Minting failed**  
Check: IPFS is filled for all tokens, ETH is on the minter (Thirdweb), the contract and recipient addresses are correct. For Crossmint, use **Staging** first.

**Endless "Please wait…" loading**  
Refresh the page (F5). If that doesn't help — let us know at w3ir@pm.me.

**Cyrillic in NFT metadata**  
Regenerate via batch/pipeline or enter traits/description in English.

**Which export format should I choose for the first drop?**
If unsure, start with **thirdweb Batch Upload** or **OpenSea / ERC-721**. They are the easiest for an EVM flow. Choose **Metaplex** only if you definitely mint on Solana through Candy Machine/Sugar.

**Can I export without IPFS?**
Yes. The ZIP already contains images and metadata. IPFS is needed when you want a `baseURI` for a contract or a mint flow that expects public URIs.

**Can I rebuild the ZIP after edits?**
Yes. Change the name, description, creator/royalty or approved works and build again. The old browser download does not update itself — download the new ZIP.

**Is it safe to enter a minter key in advanced minting?**
The key is entered in the session and is not saved as a project, but for safety use a separate minter wallet with a minimal balance, not your main treasury.

**Why don't approved images appear at stage 3?**
At stage 2 check the approval boxes and click **"Save and go to export"** — the queue fills automatically. If you approve more works later, click **"📥 Add approved work to queue"** at stage 3 to refresh the queue.

**Can I mix generated and my own images?**
Yes, but keep style, size and names consistent. It is better to add your own files at stage 3 and manually check metadata before export.

**What should I do before a public mint?**
Run a small test: 1–3 NFTs, staging or testnet, metadata check on the marketplace, then the main drop. Do not start with 1000 tokens without a test import.

---

## 8. Support

- **Email:** w3ir@pm.me — beta access, questions about credits and minting.  
- **Project site:** https://w3ir.io  
- **Legal:** [w3ir.io/legal/en](https://w3ir.io/legal/en) — one public document with three parts: **Terms of Service**, **Privacy Policy**, **Refund Policy** (UA — [w3ir.io/legal](https://w3ir.io/legal)).

Thank you for testing NFT Prompt Builder.
