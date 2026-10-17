STYLE = ("Italian trattoria kitsch sticker illustration, bold thick dark brown outline, flat warm colors "
         "(tomato red, basil green, golden yellow, cream), soft cel shading, cheerful, centered, "
         "isolated on a pure plain white background, no text, no letters, no border")
CARD = ("playing card court figure artwork, Italian trattoria kitsch style, bold thick dark brown outline, "
        "flat warm colors, cel shading, symmetrical playing-card composition, full bleed illustration, "
        "cream background, no text, no letters, no numbers, no card border")
J = []
def add(name, prompt, ratio="1:1"):
    J.append((name, prompt, ratio))

# card backs (portrait)
add("back_fr_light", "back design of a playing card: cream background with a red and white checkered trattoria "
    "tablecloth pattern, ornate golden frame, a round red medallion in the center with a plump smiling Italian chef "
    "with mustache and white toque, symmetrical, flat illustration, no text", "2:3")
add("back_fr_dark", "back design of a playing card: deep espresso brown and dark navy background with a subtle "
    "golden filigree pattern, ornate gold frame, a round gold medallion in the center with a plump smiling Italian "
    "chef with mustache and white toque, elegant night version, symmetrical, flat illustration, no text", "2:3")
add("back_it", "back design of a traditional Italian regional playing card (carte napoletane style): ornate "
    "symmetrical pattern of green and red arabesques with golden olive branches, central oval with a plump smiling "
    "Italian chef with mustache and white toque, flat vintage illustration, cream paper, no text", "2:3")

suits_fr = {"s": "spades, black", "h": "hearts, red", "d": "diamonds, red", "c": "clubs, black"}
courts = {"J": "a young Italian waiter with apron and slicked hair holding a tray",
          "Q": "a warm Italian nonna grandmother with apron and wooden spoon",
          "K": "a plump proud Italian head chef with big mustache and tall white toque"}
for r, who in courts.items():
    for s, sname in suits_fr.items():
        color = "red and cream" if "red" in sname else "black, dark green and cream"
        add(f"fr_{r}{s}", f"{CARD}, bust portrait of {who}, palette mostly {color}, a small {sname.split(',')[0][:-1]} "
            "symbol on the clothing", "2:3")

suits_it = {"d": ("denari", "golden coins"), "c": ("coppe", "golden goblets"),
            "b": ("bastoni", "wooden clubs"), "s": ("spade", "swords")}
figs = {"F": "a young page boy standing (fante) in Renaissance clothes",
        "C": "a knight riding a horse (cavallo) in Renaissance clothes",
        "R": "a seated king with crown and royal robe (re)"}
for r, who in figs.items():
    for s, (iname, obj) in suits_it.items():
        add(f"it_{r}{s}", f"{CARD}, traditional Neapolitan Italian card figure, {who}, holding one of the {obj} "
            f"of the suit {iname}, full figure", "2:3")

for s, (iname, obj) in suits_it.items():
    add(f"suit_it_{s}", f"a single traditional Italian playing card suit symbol: one of the {obj} ({iname}), {STYLE}")
for s, nm in {"s": "black spade", "h": "red heart", "d": "red diamond", "c": "black club (trefoil)"}.items():
    add(f"suit_fr_{s}", f"a single playing card suit symbol, a {nm} shape, simple bold, {STYLE}")

slots = {"spaghetti": "a plate of spaghetti with tomato sauce and a fork", "pizza": "a pizza margherita",
         "mandolino": "an Italian mandolin", "vespa": "a red vintage Vespa scooter", "moka": "a moka coffee pot",
         "pomodoro": "a shiny red tomato", "basilico": "a sprig of fresh basil leaves",
         "coin": "a big shiny gold coin embossed with a chef toque", "marione": "a plump smiling Italian chef with "
         "big mustache and white toque winking, head and shoulders, golden glow"}
for k, d in slots.items():
    add(f"slot_{k}", f"slot machine symbol icon: {d}, {STYLE}")

icons = {"home": "a cozy armchair sofa with a checkered cushion", "economy": "a stack of gold coins",
         "soundboard": "a vintage loudspeaker horn", "music": "a retro gramophone", "admin": "a chef's knife and "
         "wooden spoon crossed", "entrances": "a golden trumpet fanfare", "brain": "a cute pink brain wearing a chef "
         "toque", "settings": "a golden kitchen gear cog", "games": "a pair of dice and playing cards",
         "slot": "a red slot machine with a lever", "roulette": "a casino roulette wheel", "blackjack": "two playing "
         "cards ace and king with a casino chip", "poker5": "a fan of five playing cards", "texas": "a cowboy hat with "
         "poker chips", "chess": "a chess king piece", "briscola": "Italian playing cards with a golden coin suit",
         "scopa": "a straw broom with Italian playing cards", "tresette": "three Italian playing cards fanned",
         "settemezzo": "a seven card and a half moon", "scala40": "a run of playing cards in a row like stairs",
         "bestia": "a cute little horned beast holding playing cards", "machiavelli": "a sly Renaissance man with "
         "a feathered hat holding playing cards"}
for k, d in icons.items():
    add(f"icon_{k}", f"app icon: {d}, {STYLE}")
