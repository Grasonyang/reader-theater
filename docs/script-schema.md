# 劇本 JSON 格式

一份劇本是一個 JSON 檔，描述角色、場次與每一句台詞的講者、情緒、手勢、鏡頭。網頁依序讀取台詞，把 `audio` 與 `timestamps` 交給 TalkingHead 的 `speakAudio` 對嘴，並在台詞開始前套用情緒、手勢與鏡頭。

版本：`schema_version: 1`。讀取端是 `src/script-player.js`；第一份實際劇本是 `assets/scripts/missing-duck.json`。

## 結構

```text
Script
├─ schema_version   整數，目前為 1
├─ title            劇名
├─ characters[]     出場角色
│  ├─ id            角色代號，台詞的 speaker 用它對應
│  ├─ name          顯示名稱
│  ├─ avatar        GLB 路徑（相對於 public/）
│  └─ body          "F" 或 "M"，TalkingHead 的體型
└─ scenes[]         場次，依序演出
   ├─ id            場次代號，例如 "s1"
   ├─ title         場次名稱
   └─ lines[]       台詞，依序演出
      ├─ id         台詞代號，全劇唯一，例如 "s1-l1"
      ├─ speaker    角色 id
      ├─ text       台詞文字（英文）
      ├─ audio      處理過的 WAV 路徑（scripts/prep_audio.py 的輸出）
      ├─ timestamps 逐字時間戳 JSON 路徑（同上）
      ├─ emotion    情緒，見下表
      ├─ gesture    手勢，可省略
      │  ├─ name    手勢名稱，見下表
      │  ├─ at      從台詞開始算起幾秒時做，預設 0
      │  ├─ duration 持續秒數，預設 2
      │  └─ mirror  true 時改用右手，預設 false
      └─ camera     鏡頭，可省略（沿用上一句）
         ├─ view    鏡頭景別，見下表
         └─ target  看向哪個角色 id，可省略（預設看講者）
```

## 欄位規則

| 欄位 | 必填 | 型別 | 規則 |
|---|---|---|---|
| `schema_version` | 是 | 整數 | 目前只有 `1` |
| `title` | 是 | 字串 | |
| `characters[].id` | 是 | 字串 | 小寫英數與 `-`，全劇唯一 |
| `characters[].avatar` | 是 | 字串 | 要有 ARKit 與 Oculus 視素（viseme）blend shapes 的 Ready Player Me 相容 GLB |
| `characters[].body` | 否 | `"F"` 或 `"M"` | 預設 `"F"` |
| `scenes[].id`、`lines[].id` | 是 | 字串 | 全劇唯一；建議 `s<場>`、`s<場>-l<句>` |
| `lines[].speaker` | 是 | 字串 | 必須是 `characters[].id` 之一 |
| `lines[].text` | 是 | 字串 | 字幕與核對用；對嘴以 `timestamps` 為準 |
| `lines[].audio` | 是 | 字串 | 48 kHz 單聲道 WAV，-16 LUFS。通常由 `scripts/align_lines.py` 從整場錄音切出並寫入 |
| `lines[].timestamps` | 是 | 字串 | 逐字時間戳 JSON，時間單位是秒；`align_lines.py` 輸出的版本字用劇本原文、時間用實際錄音 |
| `lines[].emotion` | 否 | 列舉 | 預設 `"neutral"` |
| `lines[].gesture` | 否 | 物件 | 省略代表不做手勢 |
| `lines[].camera` | 否 | 物件 | 省略代表沿用上一句；第一句省略時用 `"upper"` |

### 情緒 `emotion`

直接對應 TalkingHead 的 `setMood()`：

| 值 | 說明 |
|---|---|
| `neutral` | 平靜（預設） |
| `happy` | 開心 |
| `angry` | 生氣 |
| `sad` | 難過 |
| `fear` | 害怕 |
| `disgust` | 厭惡 |
| `love` | 喜愛 |
| `sleep` | 想睡 |

### 手勢 `gesture.name`

直接對應 TalkingHead 的 `playGesture()`：`handup`（舉手）、`index`（伸食指）、`ok`、`thumbup`（比讚）、`thumbdown`（倒讚）、`side`（手往旁邊攤）、`shrug`（聳肩）、`namaste`（合十）。

### 鏡頭 `camera.view`

直接對應 TalkingHead 的 `setView()`：

| 值 | 說明 |
|---|---|
| `full` | 全身 |
| `mid` | 膝上 |
| `upper` | 腰上（預設） |
| `head` | 特寫 |

多角色同台時 `target` 才有意義，目前只有單一角色，先保留欄位。

## 範例（三句）

```json
{
  "schema_version": 1,
  "title": "Hamlet, Act 3 (reader's theater excerpt)",
  "characters": [
    { "id": "narrator", "name": "Narrator", "avatar": "avatars/brunette.glb", "body": "F" },
    { "id": "hamlet", "name": "Hamlet", "avatar": "avatars/brunette.glb", "body": "F" }
  ],
  "scenes": [
    {
      "id": "s1",
      "title": "A room in the castle",
      "lines": [
        {
          "id": "s1-l1",
          "speaker": "narrator",
          "text": "Welcome to our reader's theater.",
          "audio": "assets/audio/s1/s1-l1.wav",
          "timestamps": "assets/audio/s1/s1-l1.json",
          "emotion": "happy",
          "gesture": { "name": "handup", "at": 0.2, "duration": 1.5 },
          "camera": { "view": "upper" }
        },
        {
          "id": "s1-l2",
          "speaker": "hamlet",
          "text": "To be, or not to be, that is the question.",
          "audio": "assets/audio/s1/s1-l2.wav",
          "timestamps": "assets/audio/s1/s1-l2.json",
          "emotion": "sad",
          "gesture": { "name": "index", "at": 1.0, "duration": 2, "mirror": true },
          "camera": { "view": "head" }
        },
        {
          "id": "s1-l3",
          "speaker": "hamlet",
          "text": "Whether 'tis nobler in the mind to suffer the slings and arrows of outrageous fortune.",
          "audio": "assets/audio/s1/s1-l3.wav",
          "timestamps": "assets/audio/s1/s1-l3.json",
          "emotion": "fear",
          "gesture": { "name": "shrug", "at": 2.5 }
        }
      ]
    }
  ]
}
```

第三句省略 `camera`，所以沿用第二句的 `head` 特寫。

## 尚未決定

- 多角色同台時的站位與鏡頭切換（`target` 怎麼算）。
- 台詞之間的停頓與重疊（目前假設一句講完才下一句）。
- 是否要逐字指定情緒或手勢（目前一句一個）。
