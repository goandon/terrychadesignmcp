# Emoji Dictionary — terrycha-design MCP

Reference document for all emoji expressions, categories, and usage guidelines.
Used by both humans (for understanding) and algorithms (for expression selection).

## Base Expressions

### basic_16

| Key | Label | Label (KO) | Description | Usage Context |
|-----|-------|------------|-------------|---------------|
| happy | Happy | 기쁨 | Bright happy smiling face with sparkling eyes and wide cheerful grin | Celebrating, delighted reactions, positive announcements |
| sad | Sad | 슬픔 | Sad face with downturned mouth, teary eyes, drooping expression | Melancholy moments, sympathy, emotional vulnerability |
| angry | Angry | 화남 | Angry scowling face with furrowed eyebrows, gritted teeth, red-faced | Frustration, confrontation, strong disagreement |
| surprised | Surprised | 놀람 | Shocked surprised face with wide open eyes and mouth, hands on cheeks | Unexpected news, discovery, astonishment |
| love | Love | 사랑 | Love-struck face with heart-shaped eyes, blushing cheeks, dreamy smile | Affection, admiration, romantic feelings |
| thumbs_up | Thumbs Up | 엄지 척 | Giving enthusiastic thumbs up with winking and confident grin | Approval, encouragement, agreement |
| thinking | Thinking | 생각 중 | Thinking pose with hand on chin, one eyebrow raised, puzzled look | Consideration, contemplation, analysis |
| sleeping | Sleeping | 잠자기 | Sleeping peacefully with eyes closed, ZZZ floating, relaxed face | Rest, fatigue, dismissal through inattention |
| crying | Crying | 울음 | Crying with streams of tears, sobbing expression, watery eyes | Sorrow, disappointment, emotional release |
| laughing | Laughing | 빵 터짐 | Laughing hysterically with tears of joy, mouth wide open, holding stomach | Humor, hilarity, uncontrollable amusement |
| wink | Wink | 윙크 | Playful wink with one eye closed, tongue sticking out slightly, cute expression | Teasing, flirtation, humor, conspiratorial tone |
| embarrassed | Embarrassed | 당황 | Embarrassed blushing face with sweat drop, awkward nervous smile | Shyness, social awkwardness, self-consciousness |
| cool | Cool | 쿨 | Cool confident pose with sunglasses, smirking, finger guns | Confidence, swagger, nonchalant attitude |
| confused | Confused | 혼란 | Confused face with question marks, tilted head, squinting eyes | Uncertainty, perplexity, misunderstanding |
| excited | Excited | 신남 | Super excited with sparkle eyes, fists clenched in excitement, bouncing | Enthusiasm, anticipation, joy |
| tired | Tired | 피곤 | Exhausted droopy face with half-closed eyes, yawning, slouched posture | Fatigue, burnout, weariness |

### reaction_8

| Key | Label | Label (KO) | Description | Usage Context |
|-----|-------|------------|-------------|---------------|
| ok | OK | 오케이 | Making OK hand gesture with thumb and index finger circle, approving nod | Acceptance, confirmation, agreement |
| no | No | 노 | Shaking head no with X arms crossed, disapproving frown | Rejection, disagreement, negative response |
| please | Please | 부탁 | Begging with hands clasped together, puppy eyes, pleading expression | Requesting, appealing, hopeful asking |
| cheers | Cheers | 건배 | Raising a cup or glass in a toast, celebratory smile | Celebration, success, solidarity |
| sorry | Sorry | 미안 | Apologetic bow with hands pressed together, guilty expression | Apology, regret, remorse |
| thank_you | Thank You | 감사 | Grateful bow with hands on chest, warm appreciative smile | Gratitude, acknowledgment, appreciation |
| fighting | Fighting! | 화이팅 | Fist pump in the air, determined fierce expression, motivational pose | Encouragement, determination, go-for-it attitude |
| heart | Heart | 하트 | Making a heart shape with both hands above head, cute loving expression | Affection, love, warmth |

## Special Expression Tags

Tags that trigger auto-generation of special expressions based on character profile keywords.

| Tag | Trigger Keywords | Example Expressions | Use Case |
|-----|-----------------|---------------------|----------|
| cat_lover | cat, 고양이, 집사 | cat_hug, cat_nap, cat_play, cat_scold | Characters with feline affinity |
| bookworm | book, reading, 독서 | reading_smile, book_recommend, study_focus | Intellectual, studious characters |
| gamer | game, gaming, 게임 | victory_dance, rage_quit, controller_throw | Gaming enthusiast characters |
| foodie | food, cooking, 요리 | taste_heaven, cooking_disaster, food_coma | Food-loving characters |
| musician | music, instrument, 음악 | playing_guitar, headphones_groove, concert_excited | Music-oriented characters |
| athlete | sports, exercise, 운동 | victory_pose, stretching, high_five | Active, athletic characters |

## Expression Set Categories

### basic_16
- **Set Size**: 16 expressions
- **Use Case**: Primary emoji set for general-purpose chat stickers
- **Platform**: Discord, Telegram, Slack (standard grid)
- **Grid Layout**: 4x4 grid recommended for emoji sheets
- **Scope**: Covers emotional range from sadness to excitement, action expressions (thumbs up), and states (sleeping, thinking)

### reaction_8
- **Set Size**: 8 expressions
- **Use Case**: Action-oriented reactions and social responses
- **Platform**: Discord reactions, Telegram inline responses
- **Grid Layout**: 1x8 or 4x2 layout
- **Scope**: Hand gestures and communicative actions (ok, no, please, cheers, sorry, thank you, fighting, heart)

## Custom Expression Guidelines

### Composition Rules
- **Main character** must be the visual center (>60% of frame area)
- **Sub-characters** (pets, mascots) limited to 1 per expression
- **Props** limited to 2 per expression
- **Avoid** complex multi-character scenes (reduces chibi clarity)
- **Background elements** are NOT allowed (chroma key requirement for platform compatibility)

### Visual Standards
- **Style Consistency**: Maintain character's art style and color palette across all expressions
- **Proportions**: Chibi proportions must remain constant (2-3 head:body ratio)
- **Clarity**: Facial expression must be immediately recognizable at 512x512px (Telegram) and 64x64px (Discord)
- **Pose Variety**: Avoid repetitive poses within same expression set

### Output Format
- **Resolution**: 512x512px (scaled down to platform-specific sizes by messaging apps)
- **Format**: PNG with transparency (alpha channel required)
- **Background**: Transparent (removed during post-processing)
- **Quality**: High bitrate, no artifacts or compression noise

## Naming Conventions

### Base Expressions
- Use pre-defined key from registry (e.g., `happy`, `thumbs_up`)
- All lowercase, underscores for compound words
- Immutable within a release version

### Special Expressions
- Format: `{tag}_{action}` (e.g., `cat_hug`, `book_read`)
- Auto-generated based on character profile + concept trigger
- Stored in generation database per character/concept
- Example: Profile contains "cat_lover" → auto-generate cat_* expressions

### Custom Expressions
- Format: `cx{nn}` (e.g., `cx01`, `cx02`)
- Numeric sequence within a set (cx01-cx99)
- For user-defined free-text expressions not in base or special sets
- Short, unambiguous naming avoids collision with auto-generated keys

## File Naming Convention

### Pattern
```
{expression_key}--{grid_index:02d}.{ext}
```

### Components
- **expression_key**: Base name (happy, cat_hug, cx01)
- **--**: Double-dash separator (avoids ambiguity with underscores in key names)
- **grid_index**: Zero-padded 2-digit position in emoji grid (01-16 for basic_16, 01-08 for reaction_8)
- **ext**: File extension (png, webp, gif)

### Examples
- `happy--01.png` — First emoji in basic_16 set (position 1, typically top-left)
- `cat_hug--17.png` — Special expression, 17th in expanded custom set
- `cx01--25.png` — Custom expression, 25th overall in collection
- `fighting--08.png` — Last reaction in reaction_8 set

### Rationale
- Double-dash ensures keys with underscores don't create ambiguity (e.g., `cat_hug` vs `cat--hug`)
- Zero-padded index enables proper sorting in file managers
- Position tracking supports emoji sheet reordering without renaming

## Category Definitions

| Category | Source | Persistence | Scope | Example |
|----------|--------|------------|-------|---------|
| **base** | Pre-defined registry in server.py | Permanent, versioned per MCP release | Universal (all characters) | happy, ok |
| **special** | Auto-generated from profile+concept keywords | Per-set in generation DB, character-specific | Single character for specific concept | cat_hug (if profile triggers cat_lover) |
| **custom** | User free-text input during generation | Per-set in generation DB, concept-specific | Single character/concept combination | cx01, cx02 (user requests) |

### Persistence Model
- **Base**: Frozen in code, changes require new MCP version
- **Special & Custom**: Stored in SQLite generation history, re-creatable per character/concept
- **Migration Path**: Frequently-used custom expressions can be promoted to special (with pattern/keywords)

## Integration with terrycha-design MCP

### API Methods
- `generate_chat_emoji(character_name, expression_set, ...)` → generates base_16 or reaction_8
- `add_character_pose(prompt, reference_images, ...)` → for custom one-off expressions (outside emoji framework)
- Character profiles store expression preferences for auto-generation

### Expression Set Selection
- **basic_16**: Default for general messaging (Discord, Telegram, Slack)
- **reaction_8**: For action-oriented platforms with reaction limits
- **Custom combinations**: User-specified subset (e.g., [happy, laughing, love, wink] only)

### Storage Locations
- **Generated images**: `{output_dir}/character_emoji/{character_name}/`
- **Metadata**: SQLite in terrycha-design generation DB
- **Composite sheets**: Auto-generated preview grid (6x3 for basic_16, 4x2 for reaction_8, etc.)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-18 | Initial emoji dictionary with basic_16 and reaction_8 |

---

**Document Purpose**: This dictionary serves as both a human reference guide and algorithm input for expression selection, special tag trigger detection, and file naming consistency across the terrycha-design ecosystem.
