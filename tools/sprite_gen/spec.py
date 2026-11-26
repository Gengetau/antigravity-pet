"""Character and pose specs for regenerating the three AGY forms.

Design goal: the three forms used to be one catgirl in three colour
palettes.  Now each form gets its own species, silhouette, hair, outfit,
prop and body language, while sharing one art style and chibi proportions so
they still read as one family.
"""

from __future__ import annotations

STYLE = (
    "Cute chibi anime desktop-pet sprite in exactly the same art style, proportions and line quality as the reference image. "
    "Full body visible from head to toe, both feet visible, centered, single character only, "
    "transparent background, no ground shadow, no text, no watermark, no frame."
)

DOCK_STYLE = (
    "Cute chibi anime desktop-pet sprite in exactly the same art style, chibi head-to-body ratio, character scale and line quality as the reference image. "
    "Single character only, transparent background, NO wall, NO doorframe, NO border line, NO desk, NO ground shadow, NO text, NO watermark, NO frame."
)

DOCK_ASSETS = frozenset({"dock_peek", "dock_work", "dock_sleep", "dock_sleep_right"})

# The three forms keep their ORIGINAL catgirl designs (reference image =
# <form>/processed/masters/generated/idle_front.png).  What differs is how
# each one moves and acts.
FORMS: dict[str, dict] = {
    "carbon": {
        "name": "Carbon",
        "concept": "冷静傲娇：动作克制、幅度小、姿态端正",
        "character": (
            "The exact same catgirl as the reference: long wavy black hair fading to silver-grey at the ends, red eyes, "
            "black cat ears, dark star hair ornaments, black-and-white gothic frilly outfit, black cat tail."
        ),
        "body_language": (
            "Cool, composed and a little tsundere. Small, restrained, elegant movements; upright posture; arms often folded or hands "
            "clasped behind her back; small smiles instead of big grins; when embarrassed she looks away with a faint blush. "
            "Never wild or flailing."
        ),
    },
    "hydergon": {
        "name": "Hydrogen",
        "concept": "轻飘元气：动作轻快、常踮脚或微微浮空",
        "character": (
            "The exact same catgirl as the reference: very long fluffy white hair fading to sky blue, blue eyes, white cat ears, "
            "blue star hairclip, white-and-blue frilly outfit, fluffy white tail, a small blue wisp flame."
        ),
        "body_language": (
            "Airy, bubbly and energetic, the lightest element. Bouncy tiptoe poses, often floating slightly off the ground, "
            "arms spread wide, hair and tail drifting as if weightless, open-mouthed delighted expressions, small sparkles or bubbles nearby."
        ),
    },
    "neon": {
        "name": "Neon",
        "concept": "霓虹偶像：动作张扬、舞台感、比 V 眨眼",
        "character": (
            "The exact same catgirl as the reference: long indigo-violet hair with pink and orange gradient, purple eyes, cat ears, "
            "glowing red-orange star ornaments, black outfit with glowing orange neon lines, sparkles around her."
        ),
        "body_language": (
            "Flashy, confident idol on stage. Dynamic angled poses, hip tilt, peace signs, winks, pointing at the viewer, "
            "dramatic hair flips, glowing neon sparkles and light trails accompanying big motions."
        ),
    },
    "argon": {
        "name": "Argon",
        "concept": "慵懒惰性：动作慢悠悠、半睁眼、抱着小枕头，偶尔发出淡紫色辉光",
        "character": (
            "A NEW catgirl in the same family and art style as the reference: shoulder-length straight silky hair in pale lavender-silver "
            "with soft lilac glowing tips, sleepy half-lidded violet eyes, lavender cat ears with white inner fur, a small glowing glass "
            "discharge-tube hair clip that emits soft purple light, an oversized white-and-lavender hoodie jacket with long sleeves covering "
            "her hands and thin glowing lilac seams, a pleated grey-lilac skirt, white thigh-high socks, lavender slippers, a fluffy "
            "lavender-grey cat tail with a faintly glowing tip, lavender cat-face slippers."
        ),
        "body_language": (
            "Calm, sleepy and unbothered, the inert noble gas. Slow relaxed poses, half-closed eyes, small yawns, hands hidden in long sleeves. "
            "She almost always hugs her lavender cat-shaped pillow (sleeping cat face, small ears) against her chest; unless this frame says "
            "otherwise, keep the pillow in her arms. Reactions are mild and understated, even celebrations are lazy and cheerful. "
            "No decorative background sparkles, stars or floating particles around her unless this frame explicitly asks for an effect"
        ),
    },
    "claude": {
        "name": "Claude",
        "concept": "优雅认真：动作端庄、有条理，常拿本子或托腮思考",
        "character": (
            "The exact same girl as the reference: very long voluminous curly coral-orange hair with a small braid, amber eyes, "
            "orange flower and black ribbon hair ornament, black choker with gold pendant, white lace gothic-lolita dress with black lace corset, "
            "black bows on puffy lace sleeves, knee-length layered white ruffled skirt with gold embroidery and black lace trim, cream heeled shoes. "
            "She is a HUMAN girl: NO animal ears and NO tail. If a pose mentions a tail, use her long curly hair or skirt ruffles instead."
        ),
        "body_language": (
            "Gentle, earnest and elegant, a thoughtful young lady. Graceful composed poses, hands often clasped in front or holding a small "
            "leather notebook and pen, thinking with a finger to her chin, polite curtsies, warm sincere smiles; celebrations are joyful but refined."
        ),
    },
}

# Signature takes on some poses, per form (same frame count as ASSETS).
FORM_POSES: dict[str, dict[str, list[str]]] = {
    "claude": {
        "idle_back": ["standing, seen completely from behind (back view), long curly hair covering her back, face not visible"],
        "idle_think": ["holding a small leather notebook, pen touching her chin, looking up thoughtfully"],
        "happy": ["warm sincere smile with eyes closed, hands clasped together at her chest, a few small flower petals around"],
        "talk": ["explaining politely, one hand open palm up, the other holding a small notebook, mouth open mid-sentence"],
        "angry": ["mildly displeased, cheeks slightly puffed, hands on hips, small anger mark, still elegant"],
        "sleep": ["fast asleep lying on her stomach horizontally, head resting on an open notebook, curly hair spread out, eyes closed"],
        "tail_react": [
            "startled, someone tugged the hem of her skirt, looking back over her shoulder",
            "turning half around holding her skirt hem",
            "smoothing her skirt with both hands, slight blush",
            "back to standing, composed embarrassed smile",
        ],
        "wave": ["polite small wave with one hand at shoulder height, gentle smile", "same, hand tilted the other way",
                 "a small curtsy holding her skirt with one hand", "standing, hands clasped, warm smile"],
        "work_typing": [
            "sitting neatly with knees together, a small floating translucent screen and keyboard in front of her, left hand typing, eyes on the screen",
            "same pose, both hands lifted above the keys, focused eyes",
            "same pose, right hand typing",
            "same sitting pose, keep the floating translucent screen and keyboard exactly as in image 2, writing a note in a small notebook beside the keyboard",
        ],
    },
    "carbon": {
        "happy": ["a quiet satisfied smile, eyes softly closed, one hand raised to her cheek, faint blush"],
        "talk": ["talking calmly, one finger raised as if explaining, composed expression"],
        "angry": ["arms folded, looking away with a cold sulky glare, small anger mark"],
        "idle_think": ["arms folded, one hand on her chin, eyes narrowed in thought"],
        "wave": ["small reserved wave with one hand at shoulder height, faint smile",
                 "same, hand tilted the other way", "same, hand tilted back", "lowering her hand, looking slightly away, faint blush"],
        "celebrate": ["small fist pump at her side, restrained smile", "fist raised a little higher, eyes closed, proud",
                      "brief small hop, both feet just off the ground", "landing gracefully", "adjusting her hair, composed",
                      "arms folded, smug little smile"],
    },
    "hydergon": {
        "happy": ["floating slightly off the ground, arms spread wide, huge open-mouthed smile, bubbles around"],
        "talk": ["chattering excitedly on tiptoes, both hands waving, bubbles popping"],
        "angry": ["puffing her cheeks like a balloon, little fists up, bouncing in place"],
        "idle_think": ["floating slightly, head tilted, finger on her lips, a question-mark bubble"],
        "falling": [
            "drifting down softly mid-air like a feather, horizontally and vertically centered in the canvas, arms spread gently outward, left knee slightly raised, fluffy white-blue hair and tail floating upward, cute amazed expression",
            "same character, outfit, scale and centered framing as image 2, mid-air feather-flutter cycle frame 2: arms buoyantly waving slightly higher, right knee lifting softly while left leg trails, hair and white-blue skirt billowing to the left, amazed curious face",
            "same character, outfit, scale and centered framing as image 2, mid-air feather-flutter cycle frame 3: arms tucked lightly near shoulders, legs bicycling softly mid-air, hair and tail floating upward to the right with tiny air bubbles",
            "same character, outfit, scale and centered framing as image 2, mid-air feather-flutter cycle frame 4: arms opening back outward gracefully, hair and skirt drifting softly upward smoothly transitioning back to image 2",
        ],
        "high_five": [
            "standing horizontally centered, turned slightly three-quarter toward the right of the canvas ready for a joyful high-five: leaning lightly back on planted feet with viewer's-right arm (character's left arm) raised high and cocked back, bright excited eyes looking right, joyful anticipating smile, single character only, NO other hand, NO text",
            "same character, outfit, scale and centered footing as image 2: leaning enthusiastically forward toward the right on tiptoes with viewer's-right arm extended high and forward, open palm facing right in an energetic high-five slap, beaming wide delighted smile, single character only, NO other hand, NO text",
            "same character, outfit, scale and centered framing as image 2: cheerful bouncy recoil hop slightly on tiptoes right after the high-five slap; keep viewer's-RIGHT arm (character's left arm) raised and recoiling slightly back near her shoulder/head (strictly NO arm swap to viewer's-left side), viewer's-LEFT hand tucked cutely near her chest, happy closed '^ ^' smiling eyes with warm blush, playful knee recoil, NO disembodied hand, NO floating flame wisps, NO ground circle, NO text",
        ],
    },
    "neon": {
        "happy": ["winking with a peace sign next to her eye, hip tilted, neon sparkles"],
        "talk": ["pointing at the viewer confidently, mouth open mid-line, other hand on hip"],
        "angry": ["hands on hips, leaning forward, dramatic pout, glowing angry sparks"],
        "idle_think": ["striking a thinking pose with chin on fist like a model, one eye closed"],
        "wave": ["idol wave with arm high above her head", "arm swinging the other way, wink",
                 "blowing a kiss toward the viewer with a sparkle", "peace sign, big confident smile"],
    },
    "argon": {
        "idle_back": ["standing, seen completely from behind (back view), face not visible, fluffy tail visible, the ears of her cat pillow peeking out at her sides because she hugs it in front"],
        "idle_think": ["chin resting on top of the cat pillow she hugs, eyes half closed, looking up lazily in thought"],
        "happy": [
            "hugging the cat pillow tightly and squishing it, eyes closed in a soft content smile, small blush",
            "same pose, swaying gently to her left, cheek rubbing against the pillow",
            "same pose, swaying gently to her right, cheek rubbing against the pillow",
            "same pose, upright again, eyes closed, calm happy smile",
            "a small lazy hop on tiptoes, both feet just off the ground, still hugging the pillow",
            "landed softly, hugging the pillow, sleepy happy smile",
        ],
        "talk": ["holding the cat pillow with her left arm, right sleeve-covered hand raised slightly in a lazy gesture, mouth open mid-sentence, half-lidded eyes"],
        "angry": [
            "mildly annoyed, lower half of her face buried in the cat pillow, puffed cheeks, half-lidded glare, small anger mark",
            "same pose, squeezing the pillow tighter, anger mark a little bigger",
            "same pose, looking away with a small huff",
            "same pose, shaking her head slowly so the hair swings to one side",
        ],
        "sweep": [
            "the cat pillow tucked under her left arm, sweeping lazily with a small broom held in her right hand",
            "same pose, the broom swept out to the left side, a small puff of dust",
            "same pose, broom back in the middle, a small yawn",
            "same pose, the broom swept out to the right side, a small puff of dust",
        ],
        "sleep": ["fast asleep lying on her stomach horizontally, head resting on her cat pillow, tail curled, eyes closed"],
        "dizzy": ["dizzy, swirl eyes, wobbly stance, clutching the cat pillow, small stars circling her head"],
        "dragging": ["being lifted up from above, still clutching the cat pillow to her chest, legs dangling loosely, sleepy surprised face"],
        "falling": [
            "mid-air falling downward, horizontally and vertically centered in the canvas, clutching her lavender cat pillow tightly with both oversized-sleeve arms, knees slightly bent with left knee higher, pale lavender hair and tail streaming upward from the wind, mildly alarmed sleepy face, no floating sparkles",
            "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 2: hugging the cat pillow tighter against her chest, right knee kicked slightly higher while left slipper trails down, hair and hoodie hem fluttering to the left, mildly alarmed face",
            "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 3: hugging the cat pillow close to her chin, both legs kicking gently mid-air, hair and tail whipping upward to the right, sleepy flustered face",
            "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 4: still clutching the cat pillow securely, legs swinging smoothly back toward image 2, hair and hoodie billowing upward",
        ],
        "released_airborne": ["mid-air after being thrown, legs spread out, hugging the cat pillow, calm surprised face"],
        "poke_react": ["startled, flinching to one side, hugging the cat pillow tighter, eyes wide"],
        "tail_react": [
            "startled, tail fur puffed up, looking back over her shoulder, hugging the cat pillow",
            "turning half around to look at her tail, the pillow under one arm",
            "the pillow under her left arm, right hand holding her tail protectively, blushing",
        ],
        "eat": [
            "standing centered facing the viewer, the lavender cat pillow tucked cozily under her left arm, holding a small cute glazed star-shaped pastry cookie in her right oversized-sleeve hand at chest height, sleepy eager half-lidded eyes looking at the snack, no floating sparkles",
            "same character, outfit, scale, centered standing feet, cat pillow tucked under her left arm, and exact same pastry snack as image 2: raising the snack to her mouth with her right hand, opening her mouth to take a happy bite, sleepy bright eyes",
            "same character, outfit, scale, centered standing feet, cat pillow under her left arm, and exact same bitten snack held lower as image 2: happily chewing with her left cheek puffed cute and full, eyes softly closed in bliss, warm blush",
            "same character, outfit, scale, centered standing feet, cat pillow under her left arm, and exact same bitten snack held lower as image 2: happily chewing with her right cheek puffed cute and full, head tilted gently the other way, eyes softly closed, warm blush",
            "same character, outfit, scale, centered standing feet, and cat pillow hugged against her chest as image 2: swallowed happily, delighted sleepy smile with happy closed-arc eyes, rosy cheeks and faint cozy contentment",
        ],
        "landing": ["landing impact, deep squat, hugging the cat pillow"],
        "sleep_enter": [
            "standing upright DEAD CENTER horizontally in the exact middle of the landscape canvas (x=50%), big sleepy yawn hugging her lavender cat pillow against her chest, half-lidded drowsy eyes, both slippers planted centered",
            "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: kneeling and curling down slowly onto the ground directly beneath her standing position, drowsy, head nodding forward onto her lavender cat pillow, eyes almost closed",
            "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: curled up lying horizontally on her stomach directly in the center of the landscape canvas, head resting snugly on her lavender cat pillow, tail curled, eyes peacefully closed asleep",
        ],
        "sleep_wake": [
            "lying horizontally on her stomach DEAD CENTER in the exact middle of the landscape canvas (x=50%), head resting on her lavender cat pillow, eyes just fluttering open drowsily, tail curled",
            "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: sitting up on the ground directly in the center of the canvas hugging her lavender cat pillow with one arm while rubbing one eye sleepily with her other oversized sleeve",
            "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: standing upright DEAD CENTER in the exact middle of the landscape canvas (NOT shifted left or right), hugging her lavender cat pillow against her chest, small lazy neck stretch awake, sleepy half-lidded eyes",
        ],
        "work_typing": [
            "sitting cross-legged with the cat pillow on her lap, a small floating translucent screen and keyboard in front of her above the pillow, left hand typing, half-lidded eyes on the screen, screen light on her face",
        ],
        "sit_edge": ["sitting on an invisible ledge at the very bottom edge of the canvas, legs hanging down and cut off at the bottom, hugging the cat pillow on her lap, relaxed, left leg forward"],
        "perch_sit": [
            "sitting calmly on an invisible horizontal window ledge, facing straight toward the viewer, horizontally centered: thighs resting flat on the invisible horizontal perch line, knees together, both lower legs and lavender cat-face slippers hanging straight down side by side beneath the perch line, hugging her lavender cat pillow snugly on her lap with both oversized sleeves, sleepy content face with both half-lidded violet eyes open (NO winking), tail hanging softly behind. Keep head, shoulders, upper torso, pillow, and seated hips level and centered. Draw NO bench, NO ledge, NO wall, NO shadow, NO floating sparkles; full body including both slippers on pure transparent background",
        ],
        "perch_work": [
            "sitting on an invisible ledge, facing the viewer: thighs horizontal and pointing toward the viewer, lower legs hanging straight down side by side, "
            "the cat pillow resting on her lap, a small floating translucent screen and keyboard hovering just above the pillow, both hands on the keys typing, "
            "half-lidded eyes on the screen, calm face, tail hanging down behind. The ledge itself is NOT drawn: no bench, no wall, no shadow, only the character "
            "on a transparent background, full body including both slippers",
            "exactly the same as image 2: identical body, sitting legs, pillow, and the SAME glowing floating translucent screen and keyboard above "
            "the pillow, clearly visible; only the hands changed, both hands lifted slightly above the keys",
            "exactly the same as image 2: identical body, sitting legs hanging down, pillow, and the SAME glowing floating translucent screen and "
            "keyboard above the pillow, clearly visible; only the eyes changed, a slow calm blink with eyes closed",
        ],
        "wave": ["hugging the cat pillow with her left arm, slow lazy wave with her right sleeve at shoulder height, hand to the left, sleepy smile",
                 "same, hand in the middle", "same, hand to the right", "same, hand in the middle, soft smile"],
        "celebrate": [
            "holding the cat pillow out in front with both hands, starting to lift it",
            "lifting the pillow above her head with both arms, on tiptoes",
            "pillow held high above her head, eyes closed, lazy happy grin",
            "lowering the pillow, still smiling",
            "hugging the pillow again, satisfied",
            "hugging the pillow with one arm, sleepy peace sign with the other sleeve",
        ],
        "tired_yawn": [
            "shoulders drooping, sleepy, hugging the cat pillow",
            "starting to yawn, one sleeve covering her mouth, other arm holding the pillow",
            "biggest yawn, a tear at the corner of the eye, holding the pillow",
            "rubbing one eye with her sleeve, pillow under the other arm",
            "eyes half open, drowsy, chin on the pillow",
            "standing slightly slouched, chin resting on top of the pillow",
        ],
        "stretch": [
            "holding the cat pillow in both hands, starting to raise it",
            "stretching up on tiptoes, holding the pillow overhead with both arms fully extended (stay within canvas)",
            "same, stretching and leaning to her left with the pillow overhead",
            "same, stretching and leaning to her right with the pillow overhead",
            "hugging the pillow again, relaxed satisfied sigh",
        ],
        "high_five": [
            "standing horizontally centered, body angled slightly three-quarter toward viewer's right in a joyful high-five wind-up pose: viewer's-LEFT arm (character's right arm) steadily hugging her lavender cat plushie against her left chest/side, viewer's-RIGHT arm (character's left arm) raised and pulled back ready to high-five toward viewer's right, fluffy lavender tail poised cleanly on viewer's left, strictly two arms only, NO extra arm or third sleeve, bright eager eyes looking right, NO text",
            "same character, outfit, scale and centered footing as image 2: leaning forward toward viewer's right on tiptoes with viewer's-RIGHT arm extended forward in an energetic high-five slap while viewer's-LEFT arm keeps hugging her lavender cat plushie, fluffy lavender tail on viewer's left, strictly two arms only, NO extra arm or third sleeve, beaming smile, NO text",
            "same character, outfit, scale and centered framing as image 2: follow-through cheerful recoil hop right after high-fiving toward viewer's right; keep viewer's-RIGHT arm (character's left arm) raised and recoiling happily (do NOT swap to viewer's-left arm), viewer's-LEFT arm steadily hugging her lavender cat plushie (matching image 2), happy closed '^ ^' smile with blush, fluffy lavender tail on viewer's left, strictly two arms only, NO extra arm or third sleeve, NO text",
            "same character, outfit, scale and centered standing feet as image 2: landing smoothly back onto both slippers facing three-quarter right; STRICTLY TWO ARMS ONLY, NO extra arm, NO third sleeve; keep her right arm (on viewer's-LEFT side) cradling the sleepy purple cat plushie on the viewer's-LEFT side of her chest just like frames 1-3, and her left arm (on viewer's-RIGHT side) gently lowered/relaxed near her shoulder/chest in a happy settled grin after the high-five, fluffy lavender tail on viewer's left, strictly NO arm or plushie side swap, NO text",
        ],
        "play_dance": [
            "standing horizontally centered doing an adorable rhythmic chibi dance sway clearly toward viewer's LEFT: STRICTLY NO purple cat plushie anywhere, both oversized-sleeve arms completely empty and free of any plushie; upper body tilted cheerfully left with sleeves swaying playfully left, lifting viewer's-LEFT slipper slightly outward on tiptoe (mirroring a rightward sway), cute playful wink with one eye closed and happy open smile, fluffy lavender tail swaying on viewer's right, full body with both slippers visible, NO music notes, NO text",
        ],
        "gift_toss": [
            "standing horizontally centered facing slightly three-quarter toward viewer's right: STRICTLY NO purple cat plushie anywhere; holding one small cute glowing golden-pastel 5-pointed star orb cradled near her chest in both hands, fluffy lavender tail on viewer's left, eager sparkling eyes looking right with warm smile, both slippers planted, NO text, NO box or frame",
            "same character, outfit, scale and centered footing as image 2: STRICTLY NO purple cat plushie anywhere; leaning playfully forward toward viewer's right with viewer's-LEFT hand resting naturally near chest/hip and viewer's-RIGHT arm extending cleanly toward viewer's right tossing the same crisp glowing golden 5-pointed star orb clearly past her fingertips completely inside canvas margin, fluffy lavender tail on viewer's left (matching image 2), delighted smile, NO text",
            "same character, outfit, scale and centered standing feet as image 2: STRICTLY NO purple cat plushie anywhere; happy open-smile gaze watching toward viewer's right, small fingers of viewer's-RIGHT hand peeking cleanly out of her sleeve in an open graceful follow-through wave/send-off gesture (NOT an empty hollow cuff stub), viewer's-LEFT hand resting gently at chest, NO orb (already tossed), fluffy lavender tail on viewer's left (matching image 2), NO text",
        ],
        "summon_pop": [
            "horizontally centered magical pop-in entrance frame 1: STRICTLY NO purple cat plushie anywhere, showing her normal grey-lavender inner top and open lavender hoodie front; compact energetic mid-air tuck-crouch pose just materializing with knees tucked playfully beneath her and both slippers floating clearly above the bottom edge, oversized sleeves folded near chest, eager sparkling eyes and excited smile, fluffy lavender tail on viewer's right, pure transparent background, NO magic circle floor, NO text",
            "same character, outfit and scale as image 2, horizontally centered: STRICTLY NO purple cat plushie anywhere; joyful 'ta-da!' spring-open pop-out reveal with both arms flung wide open enthusiastically, legs extended down lightly in mid-air/tiptoe, huge sparkling happy eyes and delighted grin, pure transparent background, NO text",
            "same character, outfit and scale as image 2, horizontally centered: STRICTLY NO purple cat plushie anywhere — expose her normal grey-lavender inner top and open lavender hoodie front cleanly (NO floating or stuck plushie on chest); soft knee-bent landing squash with both slippers planted softly on the invisible ground and arms naturally opened out to sides with small hands peeking softly from sleeves for balance, bright cheerful smile, completely clean transparent background around slippers, ZERO ground shockwave, ZERO landing ring, ZERO impact arcs, ZERO aura or dust, NO text",
        ],
        "depart_poof": [
            "standing horizontally centered front-facing giving a cheerful goodbye wave: waving with viewer's-LEFT hand while hugging her lavender cat plushie with viewer's-RIGHT arm, fluffy lavender tail on viewer's right, cute wink and warm smile, both slippers planted, pure transparent background, NO text",
            "same character, outfit, scale, front-facing orientation and purple cat plushie as image 2: front-facing light cheerful anticipation hop pose (both slippers slightly lifted off the ground / one slipper springing lightly up, NOT flat-footed on the bottom edge); keep waving joyfully with viewer's-LEFT hand (character's right hand) and steadily hugging her lavender cat plushie with viewer's-RIGHT arm, fluffy lavender tail strictly on viewer's right (matching image 2), bright cheerful winking smile, NO text",
            "same character, outfit, scale, front-facing orientation and purple cat plushie as image 2: graceful mid-air joyful leap arcing upward — legs tucked playfully beneath her, waving goodbye with viewer's-LEFT hand while hugging her lavender cat plushie with viewer's-RIGHT arm, fluffy lavender tail on viewer's right, beaming smile, pure transparent background, NO text",
            "same character, outfit, scale, front-facing orientation and purple cat plushie as image 2: compact buoyant mid-air vanishing tuck-hop pose — knees pulled up tightly underneath her, eyes happily squeezed shut in a curved '^ ^' smile with light blush, BOTH oversized sleeves hugging her sleepy purple cat plushie tightly against her chest so the purple cat plushie's round lavender head and two pointy cat ears clearly peek out right under her chin (matching image 2 and reference.png), fluffy lavender tail on viewer's right, strictly NO missing plushie, pure transparent background, NO solid white circle, NO box, NO text",
        ],
    },
    "claude": {
        "high_five": [
            "standing horizontally centered, turned slightly three-quarter toward the right of the canvas ready for a joyful high-five: leaning lightly back on planted feet with viewer's-right arm raised high and cocked back, bright excited eyes looking right, joyful anticipating smile, single character only, NO other hand, NO text",
            "same character, outfit, scale and centered footing as image 2: leaning enthusiastically forward toward the right on tiptoes with viewer's-right arm extended high and forward, open palm facing right in an energetic high-five slap, beaming wide delighted smile, single character only, NO other hand, NO text",
            "same pure human girl, outfit, scale and centered framing as image 2 (NO cat ears, NO cat tail): cheerful bouncy recoil hop slightly on tiptoes right after the high-five, keeping viewer's-RIGHT arm raised and recoiling happily, eyes squeezed happily shut in a curved '^ ^' smile with warm blush; leave generous horizontal padding/margin on BOTH left and right canvas edges so ALL voluminous curly terracotta hair tips round off completely inside the frame with ZERO edge cropping, NO text",
        ],
        "summon_pop": [
            "horizontally centered magical pop-in entrance frame 1: compact energetic mid-air tuck-crouch pose just materializing, pure transparent background, NO magic circle floor, NO text",
            "same character, outfit and scale as image 2, horizontally centered: joyful 'ta-da!' spring-open pop-out reveal, pure transparent background, NO text",
            "same character, outfit and scale as image 2, horizontally centered: lively bouncy landing squash, NO ground shockwave, NO landing ring, NO impact arcs, NO aura or dust around her feet, pure clean transparent background, NO text",
            "same pure human girl, outfit and scale as image 2 (NO cat ears, NO cat tail), horizontally centered: proud upright arrival pose standing steadily on both planted cream-heeled shoes, viewer's-left hand on hip and viewer's-right hand making a clean cheerful V-sign peace gesture, confident sparkling smile; strictly clean empty transparent background around her fingers, hands and hair — ZERO floating comic marks, ZERO exclamation dots, ZERO teardrops, ZERO motion lines, ZERO sparkles, ZERO stray stickers anywhere, NO text",
        ],
        "depart_poof": [
            "pure human girl (NO cat ears, NO cat tail), standing horizontally centered facing front/slightly three-quarter right giving a bright cheerful goodbye salute/wave: raise viewer's-RIGHT arm (character's left arm) waving goodbye clearly near her head/shoulder (matching a rightward farewell wave), viewer's-LEFT arm resting naturally down by her side, cute playful wink with one eye closed and warm bright smile, both cream-heeled feet planted, leave generous horizontal margins so all voluminous curly terracotta hair tips fit completely inside the canvas, pure transparent background, NO text",
        ],
    },
}

# Extra sentence appended to every frame of an asset, per form.
FORM_NOTES: dict[str, dict[str, str]] = {
    "argon": {
        "climb_side": "Her cat pillow is tied on her back with a ribbon strap so both hands are free for climbing",
        "walk_side": "Instead of swinging her arms she keeps hugging her cat pillow against her chest with both arms; the legs move as described",
        "walk_side_stand": "hugging her cat pillow against her chest",
        "walk_start_left": "hugging her cat pillow against her chest",
        "walk_stop_left": "hugging her cat pillow against her chest",
        "transform": "hugging her cat pillow; the light is a soft lavender glow with a few lavender light motes instead of stars",
        "dock_peek": "Hugging her lavender cat pillow under her lower left arm while her right oversized-sleeve hand grips the invisible vertical edge on the left; sleepy half-lidded violet eyes (both eyes softly half-open in frame 1, closed in frame 2)",
        "dock_work": "Her lavender cat pillow tucked cozy against her chest/left side while typing lazily with her oversized sleeves on the tiny floating translucent lavender screen and keyboard; sleepy half-lidded eyes",
        "perch_sit": "Keep her lavender cat pillow hugged in the exact same position on her lap across every frame, no floating sparkles",
        "sulk": "Instead of bare crossed arms, she hugs her lavender cat pillow tightly up to her chin with her oversized sleeves, turning slightly away with puffed cheeks and a sleepy grumpy pout, no floating sparkles",
        "waiting_user": "Hugging her lavender cat pillow under her left arm while tapping sleepily toward the viewer with her right oversized-sleeve hand, sleepy curious half-lidded eyes, NO text, NO letters, NO floating sparkles",
        "jump_up": "Still clutching her lavender cat pillow safely in her arms during her buoyant lazy upward hop, oversized sleeves and hair trailing softly downward, cute cheerful sleepy smile, no floating sparkles",
        "pet_purr": "Hugging her lavender cat pillow snugly against her chest while nuzzling upward into the invisible head pat with blissful closed eyes and rosy cheeks, do NOT draw any extra hand, no floating sparkles",
        "perch_sleep": "Hugging her lavender cat pillow on her lap with her chin resting sleepily on top of the pillow, eyes softly closed, dangling legs with lavender cat-face slippers hanging straight down, no floating sparkles",
        "dock_sleep": "Her lavender cat pillow tucked cozy against her chest/cheek as she dozes peacefully hugging the invisible vertical edge on the left; both eyes softly closed in peaceful sleep, no floating sparkles",
        "refuse_food": "Holding her lavender cat pillow tucked under her left arm while waving her oversized sleeves 'no thanks' and turning her sleepy flustered face away, NO food prop, NO text, no floating sparkles",
    },
    "claude": {
        "dock_peek": "She is a HUMAN girl: NO animal ears and NO tail. Keep her coral-orange curly hair, orange flower hair ornament, and white-and-black lace dress",
        "dock_work": "She is a HUMAN girl: NO animal ears and NO tail. Keep her coral-orange curly hair, white-and-black lace dress, and a warm amber-gold floating translucent holographic screen and mini keyboard",
        "perch_sit": "She is a HUMAN girl: NO animal ears and NO tail. Instead of a tail swaying, her long coral-orange curly hair tips sway barely noticeably",
        "sleep_enter": "She is a HUMAN girl: NO animal ears and NO tail. Keep her coral-orange curly hair and white-and-black lace dress",
        "sleep_wake": "She is a HUMAN girl: NO animal ears and NO tail. Keep her coral-orange curly hair and white-and-black lace dress",
        "falling": "She is a HUMAN girl: NO animal ears and NO tail. Her long coral-orange curly hair and layered lace skirt billow upward in the wind",
        "sulk": "She is a HUMAN girl: NO animal ears and NO tail. Instead of a tail, her long coral-orange curly hair and lace skirt swish subtly",
        "waiting_user": "She is a HUMAN girl: NO animal ears and NO tail. Gently knocking politely toward the viewer with her right knuckles, NO text, NO letters",
        "jump_up": "She is a HUMAN girl: NO animal ears and NO tail. Her long coral-orange curly hair and ruffled white-and-black lace skirt trail gracefully downward",
        "pet_purr": "She is a HUMAN girl: NO animal ears and NO tail. Blissfully enjoying gentle head pats (do NOT draw any extra hand), long coral-orange curly hair swaying gently",
        "perch_sleep": "She is a HUMAN girl: NO animal ears and NO tail. Sitting gracefully on the invisible ledge with her lace skirt and dangling cream-heeled shoes, hands folded on her lap",
        "dock_sleep": "She is a HUMAN girl: NO animal ears and NO tail. Keep her coral-orange curly hair, orange flower hair ornament, and white-and-black lace dress, resting her cheek peacefully against the invisible vertical left edge with eyes softly closed",
        "refuse_food": "She is a HUMAN girl: NO animal ears and NO tail. Politely yet firmly turning her face away with a flustered expression and waving both hands 'no thank you', NO food prop, NO text",
        "high_five": "She is a HUMAN girl: NO animal ears and NO tail. Keep generous horizontal margins so all voluminous curly terracotta hair tips stay completely inside the canvas with zero edge cropping",
        "play_dance": "She is a HUMAN girl: NO animal ears and NO tail. Keep generous horizontal margins so all curly hair tips stay inside the canvas",
        "gift_toss": "She is a HUMAN girl: NO animal ears and NO tail. Keep generous horizontal margins so all curly hair tips stay inside the canvas",
        "summon_pop": "She is a HUMAN girl: NO animal ears and NO tail. Keep generous horizontal margins and strictly NO floating comic marks, dots, teardrops, or sparkles",
        "depart_poof": "She is a HUMAN girl: NO animal ears and NO tail. Keep generous horizontal margins so all curly hair tips stay inside the canvas",
    },
}


def poses(form: str, asset: str) -> list[str]:
    base = ASSETS[asset][1]
    custom = FORM_POSES.get(form, {}).get(asset)
    # A form may override only the first frames; later frames are written
    # relative to frame 1 ("same ... as image 2"), so they still fit.
    frames = base if not custom or len(custom) > len(base) else custom + base[len(custom):]
    note = FORM_NOTES.get(form, {}).get(asset)
    return [f"{frame}. {note}" for frame in frames] if note else list(frames)


PORTRAIT = "1024x1536"
LANDSCAPE = "1536x1024"

# asset id -> (size, [per-frame pose prompts]).  Right-facing walk assets are
# mirrored from the left ones and therefore not listed here.
ASSETS: dict[str, tuple[str, list[str]]] = {
    "idle_front": (PORTRAIT, [
        "standing relaxed, facing the viewer, neutral pose that shows her outfit clearly",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, feet in exactly the same place, both eyes open, hands relaxed exactly as in image 2, no wink, no hand sign, relaxed neutral standing, nothing else changed",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, feet in exactly the same place, both eyes open, hands relaxed exactly as in image 2, no wink, no hand sign, but breathing in: shoulders and chest raised very slightly, hair lifted very slightly",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, feet in exactly the same place, both eyes open, hands relaxed exactly as in image 2, no wink, no hand sign, but leaning very slightly to her left, hair (and tail if she has one) swaying a little to the left",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, feet in exactly the same place, both eyes open, hands relaxed exactly as in image 2, no wink, no hand sign, but leaning very slightly to her right, hair (and tail if she has one) swaying a little to the right",
    ]),
    "idle_back": (PORTRAIT, ["standing, seen completely from behind (back view), tail visible, face not visible"]),
    "idle_think": (PORTRAIT, [
        "standing, one finger on her chin, looking up thoughtfully, small question mark mood",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but eyes looking toward the other side",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but head tilted further and eyes closed, thinking hard",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but eyes open wide with a small idea sparkle near her head",
    ]),
    "walk_side_stand": (PORTRAIT, ["standing still in pure side view facing LEFT"]),
    "happy": (PORTRAIT, [
        "very happy, eyes closed in a big smile, both fists raised, one foot lifted",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but arms raised a little higher and hair swinging upward",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but head tilted to the other side, hair swinging the other way, an even bigger smile, no glow, aura or extra particles",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but arms slightly lower, hair and clothes settling down, no glow, aura or outline around her",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but jumping for joy: both feet clearly off the ground, knees bent, hair and skirt lifted, no glow or aura",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but just landed from a jump: knees slightly bent, hair and skirt falling back down, no glow or aura",
    ]),
    "talk": (PORTRAIT, [
        "talking, mouth open mid-sentence, one hand raised gesturing",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but mouth closed and the gesturing hand slightly lower",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but mouth wide open and the gesturing hand moved a little to the side",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but mouth half open and head tilted slightly",
    ]),
    "angry": (PORTRAIT, [
        "angry pout, puffed cheeks, fists clenched at sides, cartoon anger mark",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but stomping one foot, anger mark bigger",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but stomping with the other foot, cheeks puffed even more",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but shaking her head so the hair swings to one side",
    ]),
    "sweep": (PORTRAIT, [
        "sweeping the floor with a small broom held in both hands",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but the broom swept out to the left side, a small puff of dust",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, still holding the same broom with both hands and sweeping, the broom head back in the middle on the floor",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but the broom swept out to the right side, a small puff of dust",
    ]),
    "sleep": (LANDSCAPE, [
        "fast asleep lying on her stomach horizontally, head on folded arms, tail curled, eyes closed",
        'same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, still fast asleep with eyes fully closed, but her back slightly raised as she breathes in, a small "z" floating above her',
        'same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, still fast asleep with eyes fully closed, but mouth slightly open, a bigger "Z" floating above her',
    ]),
    "dizzy": (PORTRAIT, [
        "dizzy, swirl eyes, wobbly stance, small stars circling her head",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but her upper body leaning to the left, the stars moved around her head",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but her upper body leaning to the right, the stars moved further around",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but upright again with wobbly knees",
    ]),
    "dragging": (PORTRAIT, [
        "being lifted up from above, limbs dangling loosely, surprised face",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but kicking her legs, one leg raised",
        "same character, outfit, scale and framing as image 2, same overall pose and expression as image 2, but the other leg raised and arms flailing a little",
    ]),
    "falling": (PORTRAIT, [
        "mid-air falling downward, horizontally and vertically centered in the canvas, arms thrown up and outward, knees slightly bent with left knee higher than right, hair, skirt and tail streaming sharply upward from the wind, cute alarmed surprised face with wide eyes and small open mouth",
        "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 2: arms flailing slightly higher and wider, right knee kicked higher while left leg extends down, hair and skirt fluttering strongly to the left, cute surprised face",
        "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 3: arms tucked slightly closer near head in a cute panic flutter, legs bicycling mid-air with left leg pulled up, hair and tail whipping upward and slightly right, flustered wide-eyed face",
        "same character, outfit, scale and centered framing as image 2, mid-air falling cycle frame 4: arms swinging back outward for balance, right leg slightly forward and left leg trailing, hair and clothes billowing upward smoothly transitioning back to image 2",
    ]),
    "released_airborne": (PORTRAIT, ["mid-air after being thrown, arms and legs spread out, excited face"]),
    "idle_blink": (PORTRAIT, [
        "standing facing the viewer, eyes fully open",
        "same pose, eyes half closed",
        "same pose, eyes fully closed",
        "same pose, eyes half closed",
        "same pose, eyes fully open",
    ]),
    "idle_glance": (PORTRAIT, [
        "standing facing the viewer, eyes looking straight ahead",
        "same pose, eyes looking to her left",
        "same pose, head slightly turned to her left, curious",
        "same pose, eyes looking straight ahead",
        "same pose, eyes looking to her right",
        "same pose, head slightly turned to her right, curious",
        "same pose, eyes looking straight ahead, small smile",
    ]),
    "head_pat": (PORTRAIT, [
        "standing, looking up expectantly",
        "head tilted down a little, eyes half closed, slight blush",
        "eyes closed happily, ears flattened, blush, tiny hearts",
        "eyes closed, leaning into the pat, big blush",
        "eyes opening, content smile, blush",
        "back to standing, happy smile",
    ]),
    "poke_react": (PORTRAIT, [
        "startled, flinching to one side, eyes wide",
        "leaning away, puffed cheeks",
        "looking back with an annoyed pout",
        "recovering to standing, small huff",
    ]),
    "tail_react": (PORTRAIT, [
        "startled, tail fur puffed up, looking back over her shoulder",
        "spinning half around to look at her tail",
        "holding her tail protectively, blushing",
        "back to standing, embarrassed smile",
    ]),
    "eat": (PORTRAIT, [
        "standing centered facing the viewer, happily holding a cute small glazed star-shaped pastry cookie in both hands at chest height, eyes sparkling eagerly looking at the snack with a happy smile",
        "same character, outfit, scale, centered standing feet and exact same pastry snack as image 2: raising the snack up to her mouth, opening her mouth wide to take a big happy bite, eager bright eyes",
        "same character, outfit, scale, centered standing feet and exact same bitten snack held lower at chest height as image 2: happily chewing with her left cheek puffed cute and full, eyes closed happily in bliss, warm rosy blush",
        "same character, outfit, scale, centered standing feet and exact same bitten snack held at chest height as image 2: happily chewing with her right cheek puffed cute and full, head tilted gently the other way, happy closed eyes, warm rosy blush",
        "same character, outfit, scale and centered standing feet as image 2: swallowed happily, hands clasped warmly near chest, delighted radiant smile with joyful closed-arc eyes, rosy cheeks and tiny happy sparkles",
    ]),
    "landing": (PORTRAIT, [
        "landing impact, deep squat, arms out for balance",
        "half rising from the squat",
        "standing up again, steady",
    ]),
    "sleep_enter": (LANDSCAPE, [
        "standing upright DEAD CENTER horizontally in the exact middle of the landscape canvas (x=50%, NOT on the left or right edge), big drowsy yawn, rubbing one eye sleepily, both feet planted centered",
        "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: kneeling and curling down gently onto the ground directly beneath her standing position, very drowsy, head nodding forward, eyes half closed",
        "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: curled up lying horizontally on her stomach directly in the center of the landscape canvas, head resting on folded arms, tail curled, eyes peacefully closed falling asleep",
    ]),
    "sleep_wake": (LANDSCAPE, [
        "lying horizontally on her stomach DEAD CENTER in the exact middle of the landscape canvas (x=50%), head resting on folded arms, tail curled, eyes just fluttering open drowsily",
        "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: sitting up on the ground directly in the center of the canvas, rubbing one eye sleepily with a small drowsy yawn",
        "same character, outfit, scale and DEAD CENTER horizontal alignment (x=50%) as image 2: standing upright DEAD CENTER in the exact middle of the landscape canvas (NOT shifted to the left or right), cute sleepy stretch awake with arms raised gently, bright waking smile",
    ]),
    "walk_side": (PORTRAIT, [
        "walking in pure side view facing LEFT, a big lively stride: left leg stepping far forward with the heel just touching the ground, right leg stretched far behind, right arm swinging forward, left arm swinging back, hair and tail trailing behind",
        "same character and framing, side view facing LEFT, clearly different leg and arm positions from image 2: weight on the front left leg with the knee bent, body at its lowest, right foot peeling off the ground behind, arms passing the body",
        "same character and framing, side view facing LEFT, clearly different leg and arm positions from image 2: right leg swinging forward with the knee raised high, standing tall on the straight left leg, body at its highest, hair and skirt bouncing up",
        "same character and framing, side view facing LEFT, clearly different leg and arm positions from image 2: right leg stepping far forward with the heel just touching the ground, left leg stretched far behind, left arm swinging forward, right arm swinging back",
        "same character and framing, side view facing LEFT, clearly different leg and arm positions from image 2: weight on the front right leg with the knee bent, body at its lowest, left foot peeling off the ground behind, arms passing the body",
        "same character and framing, side view facing LEFT, clearly different leg and arm positions from image 2: left leg swinging forward with the knee raised high, standing tall on the straight right leg, body at its highest, hair and skirt bouncing up",
    ]),
    "walk_start_left": (PORTRAIT, [
        "side view facing LEFT, leaning forward to start walking",
        "side view facing LEFT, first step forward",
    ]),
    "walk_stop_left": (PORTRAIT, [
        "side view facing LEFT, braking, leaning back slightly",
        "side view facing LEFT, standing still, settled",
    ]),
    # ----- new autonomy actions (see docs/ACTION_DESIGN.md) -----
    "work_typing": (PORTRAIT, [
        "sitting cross-legged, a small floating translucent screen and keyboard in front of her, left hand typing, eyes on the screen, screen light on her face",
        "same pose, both hands lifted above the keys, focused eyes",
        "same pose, right hand typing",
        "same sitting pose, keep the floating translucent screen and keyboard exactly as in image 2, hands resting on the keys, head tilted looking at the screen, tail swaying",
    ]),
    "sit_edge": (PORTRAIT, [
        "sitting on an invisible ledge at the very bottom edge of the canvas, legs hanging down and cut off at the bottom, relaxed, left leg forward",
        "same pose, right leg forward, tail hanging down",
        "same pose, eyes closed in a slow blink",
    ]),
    # Climbing a window's side edge.  She faces LEFT with the (invisible) wall
    # just left of her; the right-facing copy is mirrored (MIRRORS).
    "climb_side": (PORTRAIT, [
        "climbing straight up an invisible vertical wall that is just to her LEFT, seen in pure side view facing LEFT toward the wall, body close to the wall, "
        "left hand reaching high up and pressed flat against the wall, right hand gripping at chest height, right knee raised high with the foot pressed against the wall, "
        "left leg stretched down, determined face, tail hanging down. Draw NO wall, NO ledge, NO rope and NO shadow: only the character on a transparent background",
        "same character, outfit, scale and framing as image 2, still climbing the invisible wall on her LEFT in side view facing LEFT: both hands now gripping at head height, "
        "body pulled up higher, both knees bent with feet against the wall. No wall drawn",
        "same character, outfit, scale and framing as image 2, still climbing in side view facing LEFT: right hand reaching high up against the wall, left hand at chest height, "
        "left knee raised high, right leg stretched down (the mirror of image 2's limbs). No wall drawn",
        "same character, outfit, scale and framing as image 2, still climbing in side view facing LEFT: both hands at head height, legs pushing up straight, a small effort sweat drop. No wall drawn",
    ]),
    # Sitting on a window's top edge with the legs hanging over the front.
    "perch_sit": (PORTRAIT, [
        "sitting calmly on an invisible horizontal window ledge, facing straight toward the viewer, horizontally centered: thighs resting flat on the invisible horizontal perch line, knees together, both lower legs and shoes hanging straight down side by side beneath the perch line, "
        "both hands resting lightly on the invisible ledge beside her hips, relaxed happy face with BOTH eyes open (NO winking), tail hanging softly behind. Keep head, shoulders, upper torso, and seated hips level and centered. "
        "The ledge itself is NOT drawn: no bench, no wall, no shadow, only the character on a transparent background, full body including both shoes",
        "EXACTLY the same as image 2: pixel-locked identical head position, head angle, open eyes, facial expression, hair, shoulders, upper torso, arms, hands, and seated hip height at the exact same vertical and horizontal coordinates — DO NOT stand up, DO NOT tilt head, DO NOT move torso or hips even slightly. "
        "ONLY change her dangling lower legs below the knees and tail: swing her left lower calf and left shoe gently forward and slightly upward while her right calf hangs slightly back, tiny gentle tail sway to the left",
        "EXACTLY the same as image 2: pixel-locked identical head position, head angle, hair, shoulders, upper torso, arms, hands, and seated hip height at the exact same vertical and horizontal coordinates — DO NOT stand up, DO NOT tilt head, DO NOT move torso or hips even slightly. "
        "Both lower legs and shoes hanging straight down side by side exactly like image 2, ONLY change her eyes to a gentle natural blink (both eyes softly closed with a peaceful smile) and subtle neutral tail position",
        "EXACTLY the same as image 2: pixel-locked identical head position, head angle, open eyes, facial expression, hair, shoulders, upper torso, arms, hands, and seated hip height at the exact same vertical and horizontal coordinates — DO NOT stand up, DO NOT tilt head, DO NOT move torso or hips even slightly. "
        "ONLY change her dangling lower legs below the knees and tail: swing her right lower calf and right shoe gently forward and slightly upward while her left calf hangs slightly back, tiny gentle tail sway to the right",
    ]),
    "perch_work": (PORTRAIT, [
        "sitting on an invisible ledge, facing the viewer: thighs horizontal and pointing toward the viewer, lower legs hanging straight down side by side, "
        "a small floating translucent screen and keyboard hovering just above her lap, both hands on the keys typing, eyes on the screen, calm focused face, "
        "tail hanging down behind. The ledge itself is NOT drawn: no bench, no wall, no shadow, only the character on a transparent background, full body including both shoes",
        "exactly the same as image 2: identical body, head, hair, legs and screen position; only the hands changed, both hands lifted slightly above the keys",
        "exactly the same as image 2: identical body, head, hair, legs and screen position; only the eyes changed, a slow calm blink with eyes closed",
        "exactly the same as image 2: identical body, head, hair, legs and screen position; only the hands changed, right hand pressing a key, a tiny satisfied smile",
    ]),
    "celebrate": (PORTRAIT, [
        "crouching down to prepare a jump, excited",
        "jumping up, both arms raised high",
        "at the top of the jump, eyes closed with a huge grin",
        "coming down, arms still up",
        "landing with a small knee bend",
        "standing, victory pose with a peace sign or fist",
    ]),
    "tired_yawn": (PORTRAIT, [
        "shoulders drooping, sleepy",
        "starting to yawn, one hand covering mouth",
        "biggest yawn, a tear at the corner of the eye",
        "rubbing one eye with a fist",
        "eyes half open, drowsy",
        "standing slightly slouched, low energy",
    ]),
    "stretch": (PORTRAIT, [
        "hands clasped together, starting to raise them",
        "stretching up on tiptoes, arms fully extended overhead (stay within canvas)",
        "stretching and leaning to her left",
        "stretching and leaning to her right",
        "arms down, satisfied relaxed sigh",
    ]),
    "wave": (PORTRAIT, [
        "facing the viewer, right hand raised waving, hand to the left",
        "same, hand in the middle, smiling",
        "same, hand to the right",
        "same, hand in the middle, bright smile",
    ]),
    "transform": (PORTRAIT, [
        "facing the viewer, glowing light starting to wrap around her",
        "turning to side view, wrapped in bright light of her theme colours",
        "seen from behind, silhouette almost fully covered by glowing light",
        "turning back to side view, light fading",
        "facing the viewer, signature pose, light sparkles dispersing",
    ]),
    # ----- screen-edge docking (left screen edge; mirrored for right screen edge) -----
    "dock_peek": (PORTRAIT, [
        "peeking out playfully to the RIGHT from behind an invisible vertical wall on her LEFT side: keep her chibi head size and vertical three-quarter body scale matching the reference image (head, upper torso, waist, skirt/outfit and flowing hair/tail visible down to mid-thigh, legs hidden behind the left edge). "
        "Her left shoulder, left side of her torso and skirt end flush along one clean straight vertical cut on the far left of her silhouette as if emerging from behind a monitor bezel. "
        "Both hands wrap around and grip that invisible vertical left edge (upper hand near shoulder height, lower hand near waist height), head tilted playfully to the right looking directly at the viewer with BOTH eyes wide open, bright curious gaze and a warm smile (NO winking, NO closed eyes). "
        "Draw NO wall, NO line, NO frame, NO shadow; pure transparent background",
        "exactly the same as image 2: identical character, identical straight vertical left-edge flush cut, identical hands gripping the invisible left edge, identical scale, framing and outfit; "
        "only her expression changed to a cheerful gentle blink with both eyes softly closed in a happy smile and hair swaying slightly",
    ]),
    "dock_work": (PORTRAIT, [
        "peeking out sideways to the RIGHT from behind an invisible vertical wall on her LEFT side while working: keep her chibi head size and vertical three-quarter body scale matching the reference image (head, upper torso, waist, skirt/outfit and flowing hair/tail visible down to mid-thigh, legs hidden behind the left edge). "
        "Her left shoulder and left side of her torso/skirt end flush along one clean straight vertical cut on the far left of her silhouette as if leaning out from behind a monitor bezel. "
        "Leaning out to the right, a small glowing floating translucent holographic screen (showing ONLY abstract glowing geometric UI bars/icons, NO letters, NO numbers, NO text) and mini keyboard hover in front of her chest on the right side, left hand pressing a key on the floating keyboard, right hand hovering above the keys, focused bright eyes looking at the floating screen with soft screen light on her face. "
        "Draw NO wall, NO line, NO desk, NO frame, NO shadow; pure transparent background",
        "exactly the same as image 2: identical character, identical straight vertical left-edge flush cut, identical scale, framing, body and the SAME glowing floating translucent screen (abstract UI icons only, no text) and mini keyboard in the exact same position; "
        "only her hands changed: right hand pressing a key on the floating keyboard, left hand lifted slightly above the keys, focused eyes on the screen",
        "exactly the same as image 2: identical character, identical straight vertical left-edge flush cut, identical scale, framing, body and the SAME glowing floating translucent screen (abstract UI icons only, no text) and mini keyboard in the exact same position; "
        "only her eyes and hands changed: both hands resting on the keys, a calm happy slow blink with eyes closed and a tiny satisfied smile",
    ]),
    "dock_sleep": (PORTRAIT, [
        "clinging sleepily to an invisible vertical wall on her LEFT side, facing slightly to the RIGHT: keep her chibi head size and vertical three-quarter body scale matching the reference image (head, upper torso, waist, skirt/outfit and flowing hair/tail visible down to mid-thigh, legs hidden behind the left edge). "
        "Her left cheek, left shoulder, and left side of her torso and skirt rest flush along one clean straight vertical cut on the far left of her silhouette as if hugging and resting her cheek sleepily against a monitor bezel. "
        "Both arms wrap snugly around the invisible vertical left edge (upper hand near cheek/shoulder height, lower hand near waist height), cheek gently pressed against the vertical edge, both eyes peacefully closed in sweet sleep, soft relaxed smile, hair and tail resting calmly downward. "
        "Draw NO wall, NO line, NO frame, NO shadow, NO text, NO floating Z letters; pure transparent background",
        "exactly the same as image 2: identical character, identical straight vertical left-edge flush cut, identical arms hugging the invisible left edge, identical scale, framing and outfit; "
        "still peacefully asleep with both eyes gently closed, breathing in softly: chest and shoulders risen very slightly, head nestled a tiny fraction more snugly into the left edge, hair tips swaying subtly, NO text, NO floating Z letters",
        "exactly the same as image 2: identical character, identical straight vertical left-edge flush cut, identical arms hugging the invisible left edge, identical scale, framing and outfit; "
        "still peacefully asleep with both eyes gently closed, exhaling softly: shoulders settled gently down, tiny peaceful content sigh expression, hair and tail relaxed downward, NO text, NO floating Z letters",
    ]),
    # ----- v3.1 Batch 3 high-charm companion actions -----
    "sulk": (PORTRAIT, [
        "standing centered facing three-quarters slightly turned away, adorable pouting sulk: arms crossed tightly over her chest, cheeks puffed out cutely, pouty frown and slightly furrowed brows glancing sideways with a grumpy little huff, tail curled tightly low, both feet planted",
        "same character, outfit, scale, centered framing and sulking crossed-arms pose as image 2: cheeks puffed slightly fuller, tapping her right toe impatiently on the ground, tail flicking sharply to the left in a tiny grumpy fidget",
        "same character, outfit, scale, centered framing and sulking crossed-arms pose as image 2: shifting weight slightly onto her other foot, turning her shoulder and chin a touch further away while peeking side-eye toward viewer, pouty frown, tail flicking to the right",
        "same character, outfit, scale, centered framing and sulking crossed-arms pose as image 2: shoulders settling slightly in a cute stubborn pout, cheeks still softly puffed, both feet planted, tail swishing back low",
    ]),
    "waiting_user": (PORTRAIT, [
        "standing centered facing straight toward the viewer, leaning slightly forward curiously with eager wide sparkling eyes and an expectant cheerful smile, raising her right hand/knuckles gently forward toward the viewer as if playfully about to knock on an invisible glass screen (other hand relaxed at side). Draw NO glass pane, NO border, NO speech bubble, NO text, NO letters, NO symbols anywhere",
        "same character, outfit, scale and centered framing as image 2: leaning slightly closer toward the viewer, her raised right hand/knuckles tapping forward against the invisible glass screen (first playful knock) with tiny pure abstract curved motion lines (NO text, NO letters, NO glass frame), bright eager wide eyes",
        "same character, outfit, scale and centered framing as image 2: pulling her raised right hand back slightly preparing to tap a second time, head tilted playfully with an expectant cute smile and wide curious eyes, NO text, NO letters, NO glass frame",
        "same character, outfit, scale and centered framing as image 2: tapping forward a second time with her raised right hand/knuckles against the invisible screen (second playful knock) with tiny pure abstract motion lines, leaning eagerly with bright wide eyes and cute open-mouth smile, NO text, NO letters, NO glass frame",
    ]),
    "jump_up": (PORTRAIT, [
        "horizontally centered, energetic confident launch crouch preparing to leap upward: knees bent low, body coiled downward, arms pulled back for momentum, excited bright eyes and determined cheerful smile, hair and skirt gathered cleanly",
        "same character, outfit, scale and horizontally centered framing as image 2: mid-air joyful upward soar, both feet lifted high off the ground, both arms stretched joyfully upward, knees slightly tucked, hair, skirt and tail streaming straight downward behind her, bright joyful grin",
        "same character, outfit, scale and horizontally centered framing as image 2: at the peak apex stretch of the upward leap in mid-air, body extended sleekly upward with one knee raised and one leg trailing downward, arms reaching triumphantly up, hair and tail trailing cleanly downward, sparkling triumphant smile",
    ]),
    "pet_purr": (PORTRAIT, [
        "standing centered facing the viewer, blissfully enjoying gentle head pats (single character only, do NOT draw any extra hand): eyes squeezed happily shut in joyful curved arcs, warm rosy blushing cheeks, cute content smile, head tilting slightly upward and nuzzling gently to the left, hands clasped happily near her chest, ears angled comfortably, tail swaying softly to the left",
        "same character, outfit, scale, centered standing feet and blissful expression as image 2 (do NOT draw any extra hand): nuzzling her head gently upward a tiny bit higher into the invisible head pat with happy squeezed-shut curved eyes, warm rosy blush, ears twitching playfully slightly lowered, tail curling softly upward to the left",
        "same character, outfit, scale, centered standing feet and blissful expression as image 2 (do NOT draw any extra hand): gently tilting and nuzzling her head to the right with joyful squeezed-shut curved eyes, warm rosy cheeks, happy purring smile, ears perked softly, tail swaying smoothly to the right",
        "same character, outfit, scale, centered standing feet and blissful expression as image 2 (do NOT draw any extra hand): settling softly centered with chin slightly lifted in pure bliss, eyes squeezed happily shut in curved arcs, warm rosy blush, tail curving softly back toward center",
    ]),
    "perch_sleep": (PORTRAIT, [
        "sitting peacefully asleep on an invisible horizontal window ledge, facing toward the viewer, horizontally centered (matching perch_sit seated hip line and scale): thighs resting flat on the invisible horizontal perch line, knees together, both lower legs and shoes hanging relaxed straight down side by side beneath the perch line, hands resting softly on her lap/thighs, head nodding gently forward and tilted slightly dozing peacefully with both eyes softly closed, calm sleeping expression, tail hanging relaxed behind. Draw NO bench, NO ledge, NO wall, NO shadow, NO text, NO floating Z letters; full body including both shoes on pure transparent background",
        "EXACTLY the same as image 2: pixel-locked identical seated hip height, thighs, dangling lower legs, shoes, hands, and outfit on the invisible horizontal perch line; ONLY gentle slow breathing inhale: shoulders and chest rising very slightly, head nodding a tiny fraction deeper forward dozing peacefully with eyes softly closed, tail barely swaying, NO text, NO floating Z letters",
        "EXACTLY the same as image 2: pixel-locked identical seated hip height, thighs, dangling lower legs, shoes, hands, and outfit on the invisible horizontal perch line; ONLY gentle slow breathing exhale: shoulders settling softly back down, head bobbing subtly upward a tiny fraction still peacefully asleep with eyes softly closed and a faint content sleeping smile, NO text, NO floating Z letters",
    ]),
    "refuse_food": (PORTRAIT, [
        "standing centered, playfully refusing food: leaning upper body slightly back and turning her face away to her left with a cute flustered scrunched-up 'no thanks' expression (squinting eyes, cute wavy grimace/frown, light blush), raising BOTH open palms in front of her waving 'no no', both feet planted, NO food prop, NO text",
        "same character, outfit, scale and centered standing feet as image 2: shaking her head slightly the other way with eyes squeezed tightly shut and a cute flustered disgusted pout, waving both open hands briskly to the right in an emphatic 'no thanks!' gesture, hair swinging slightly, NO food prop, NO text",
        "same character, outfit, scale and centered standing feet as image 2: turning her face away again with cheeks puffed in a cute stubborn 'nope!' frown, waving both open hands back to the left defensively, NO food prop, NO text",
    ]),
    "high_five": (PORTRAIT, [
        "standing horizontally centered, turned slightly three-quarter toward the right of the canvas ready for a joyful high-five: leaning lightly back on planted feet with her right open palm raised high and cocked back near her right shoulder, bright excited eyes looking right, joyful anticipating smile, single character only, NO other hand, NO text",
        "same character, outfit, scale and centered footing as image 2: leaning enthusiastically forward toward the right on tiptoes with her right arm extended high and forward, open palm facing right in an energetic high-five slap, beaming wide delighted smile, hair and outfit swaying forward, single character only, NO other hand, NO text",
        "same character, outfit, scale and centered framing as image 2: cheerful bouncy recoil hop slightly on tiptoes right after the high-five, eyes squeezed happily shut in a curved '^ ^' joyful smile with warm blush, raised right hand relaxing happily, hair and skirt bouncing upward, NO text",
        "same character, outfit, scale and centered standing feet as image 2: landing smoothly back onto both planted feet facing three-quarter right with bright sparkling eyes, proud cheerful grin and playful relaxed hands, NO text",
    ]),
    "play_dance": (PORTRAIT, [
        "standing horizontally centered doing an adorable rhythmic chibi dance sway to the left: upper body tilted cheerfully left, both hands raised playfully to the left side, cute playful wink with one eye closed and happy open smile, left foot tapped playfully outward on tiptoe, full body with both shoes visible, NO music notes, NO text",
        "same character, outfit, scale and centered framing as image 2: bouncy rhythmic center clap — knees softly bent in a cute dip, both hands clapping cheerfully together in front of her chest, head upright with big sparkling happy eyes and beaming smile, both feet planted, NO music notes, NO text",
        "same character, outfit, scale and centered framing as image 2: adorable rhythmic dance sway to the right — upper body tilted cheerfully right, both hands raised playfully to the right side, sparkling joyful eyes and bright smile, right foot tapped playfully outward on tiptoe, both shoes visible, NO music notes, NO text",
        "same character, outfit, scale and centered framing as image 2: cheerful little upbeat dance hop rising lightly onto tiptoes centered, both hands raised cheerfully in cute peace/cheer poses, hair and skirt fluttering upward joyfully, bright happy smile, NO music notes, NO text",
    ]),
    "gift_toss": (PORTRAIT, [
        "standing horizontally centered facing slightly three-quarter toward the right, holding one small cute glowing golden-pastel star orb cradled near her chest in both hands, eager sparkling eyes looking right with a playful warm smile, both feet planted, NO text, NO box or frame",
        "same character, outfit, scale and centered footing as image 2: leaning playfully forward toward the right with her right arm extended forward mid-toss releasing the same small glowing golden-pastel star orb just past her fingertips toward the right, hair and outfit swinging forward with a delighted smile, NO text",
        "same character, outfit, scale and centered standing feet as image 2: cheerful follow-through pose watching toward the right with right hand still lightly raised forward and proud happy smiling eyes, NO orb in her hands (already tossed), NO text",
    ]),
    "summon_pop": (PORTRAIT, [
        "horizontally centered magical pop-in entrance frame 1: compact energetic mid-air tuck-crouch pose just materializing — knees tucked playfully beneath her, arms gathered close in front of chest, eager sparkling eyes and excited smile, hair and outfit puffed slightly inward, pure transparent background, NO magic circle floor, NO text",
        "same character, outfit and scale as image 2, horizontally centered: joyful 'ta-da!' spring-open pop-out reveal — both arms flung wide open enthusiastically, legs extended down lightly in mid-air/tiptoe, huge sparkling happy eyes and wide delighted grin, hair and outfit fluttering dynamically outward, pure transparent background, NO text",
        "same character, outfit and scale as image 2, horizontally centered: lively bouncy landing squash — both feet landing softly on the invisible ground with knees bent slightly, arms out playfully for balance, hair and skirt bouncing downward, bright cheerful smile, NO ground shockwave, NO landing ring, NO impact arcs, NO aura or dust around her feet, pure clean transparent background, NO text",
        "same character, outfit and scale as image 2, horizontally centered: proud upright arrival pose standing steadily on both planted feet, one hand on hip and the other giving a cute cheerful peace sign / wave, confident sparkling smile ready for action, NO text",
    ]),
    "depart_poof": (PORTRAIT, [
        "standing horizontally centered giving a bright cheerful goodbye salute/wave: right hand raised near her forehead/cheek waving goodbye, cute playful wink with one eye closed and warm bright smile, left hand relaxed, both feet planted, pure transparent background, NO text",
        "same character, outfit, scale and centered framing as image 2: playful anticipation crouch turning three-quarter right preparing to hop away, knees bent lightly, glancing cheerfully back over her shoulder with a cute waving hand and happy grin, NO text",
        "same character, outfit, scale and centered framing as image 2: graceful mid-air joyful leap arcing upward and right — legs tucked playfully beneath her, one hand raised waving goodbye, hair and outfit trailing dynamically behind with a big beaming smile, pure transparent background, NO text",
        "same character, outfit, scale and centered framing as image 2: compact buoyant mid-air tuck-hop dissolving cheerfully away — arms and knees tucked in a cute floating leap, eyes happily squeezed shut in a curved '^ ^' smile with light blush, fluttering hair and ribbons, pure transparent background, NO solid white circle, NO text",
    ]),
}

MIRRORS = {
    "climb_side_right": "climb_side",
    "walk_side_right": "walk_side",
    "walk_start_right": "walk_start_left",
    "walk_stop_right": "walk_stop_left",
    "dock_peek_right": "dock_peek",
    "dock_work_right": "dock_work",
    "dock_sleep_right": "dock_sleep",
}


def total_frames() -> int:
    return sum(len(frames) for _size, frames in ASSETS.values())


SKIP_REGENERATE = {"idle_front"}  # it is the reference image itself

# Frame 0 of these is only a seed for the later frames and is not played:
# a frame redrawn from the reference alone looks slightly different from
# frames derived from it, which would pop in a loop.
DROP_FIRST = {"idle_front"}

# Play only the first N (kept) frames.  Idle is shown most of the time and
# regenerated frames differ slightly in hair detail, which reads as jitter in a
# loop; like the upstream pet it uses one frame plus procedural breathing.
KEEP_FRAMES = {"idle_front": 1}
