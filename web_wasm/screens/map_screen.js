import {
  buildRenderRows,
  buildEncounterSelection,
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
  shouldTriggerEncounter,
} from "../map_data.js";
import {
  asArray,
  buildSpellLevelByName,
  buildRecoveredPartySnapshot,
  clone,
  loadJson,
  persistMenuStateFromEnvelope,
  resolveInventoryBucketForItem,
  syncMenuPartyRecovery,
  syncSavePartyRecovery,
} from "../location_shared.js";
import {
  isCidGuestActive,
  isSaraGuestActive,
  resolveActiveGuestFollowerType,
} from "../guest_companion.js";
import { mergeMenuStateIntoSave } from "../menu_save_sync.js";
import { triggerAutoSaveFromEnvelope } from "./screen_shared.js";
import { configureAmbientAudioSession } from "../audio_session.js";
import { playManagedBgm } from "../audio_output.js";

const DISPLAY_TILE_SIZE = 22;
const CHARACTER_SOURCE_TILE_SIZE = 16;
const CHARACTER_DISPLAY_SCALE = 1.5;
const CHARACTER_DISPLAY_TILE_SIZE = CHARACTER_SOURCE_TILE_SIZE * CHARACTER_DISPLAY_SCALE;
const CHARACTER_SHEET_COLUMNS = 6;
const NPC_SOURCE_TILE_SIZE = 16;
const NPC_DISPLAY_SCALE = 1.5;
const NPC_DISPLAY_TILE_SIZE = NPC_SOURCE_TILE_SIZE * NPC_DISPLAY_SCALE;
const NPC_SHEET_COLUMNS = 6;
const NPC_FRAME_MS = 1000;
const NPC_DIRECTION_MIN_MS = 3000;
const NPC_DIRECTION_MAX_MS = 6000;
const NPC_DIRECTIONS = ["up", "left", "right", "down"];
const NPC_MOVEMENT_RANDOM = "random";
const WATER_ANIMATION_GIDS = new Set([5, 6, 9, 10, 11, 14, 15, 16, 30, 31, 32, 43, 46, 47, 48]);
const WATER_FLOW_TILE_GIDS = new Set([31]);
const WATER_ANIMATION_GIDS_BY_TILESET_NAME = {
  "TILESET - Ur": new Set([6, 9, 10, 11, 14, 15, 16, 30, 43, 46, 47, 48]),
  "TILESET - Kazus": new Set([5, 6, 9, 10, 11, 14, 16, 43, 46, 47, 48]),
  "TILESET - FloatingContinent": new Set([5, 9, 10, 11, 14, 15, 16, 25, 26, 30, 31, 32, 46, 47, 48, 59, 67]),
};
const WATER_FLOW_TILE_GIDS_BY_TILESET_NAME = {
  "TILESET - Ur": new Set([]),
  "TILESET - Kazus": new Set([]),
  "TILESET - FloatingContinent": new Set([31]),
};
const WATER_HIGHLIGHT_SHIFT_PX = 4;
const WATER_FLOW_SHIFT_PX = DISPLAY_TILE_SIZE;
const WATER_FLOW_ANIMATION_MS = Math.round(1800 * (WATER_FLOW_SHIFT_PX / WATER_HIGHLIGHT_SHIFT_PX));
const MAP_MOVE_ANIMATION_MS = 140;
const HOLD_MOVE_INITIAL_DELAY_MS = 220;
const HOLD_MOVE_REPEAT_MS = 110;
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";
const MAP_ENTRY_CONTEXT_KEY = "ff3_wasm_map_entry_context_v1";
const SHOP_START_CONTEXT_KEY = "ff3_wasm_shop_start_context_v1";
const ALTER_CAVE_B3_INTRO_EVENT_FLAG = "altar_cave_b3_intro_complete";
const ALTER_CAVE_B3_INTRO_MAP_ID = "Alter_Cave_B3";
const FLOATING_CONTINENT_MAP_ID = "FloatingContinent";
const FLOATING_CONTINENT_BGM_URL = new URL("../../assets/sounds/bgm/eternal-wind.ogg", import.meta.url).href;
const UR_BGM_URL = new URL("../../assets/sounds/bgm/Hometown of Ur.ogg", import.meta.url).href;
const KAZUS_BGM_URL = new URL("../../assets/sounds/bgm/jinn-the-fire.ogg", import.meta.url).href;
const ALTER_CAVE_BGM_URL = new URL("../../assets/sounds/bgm/crystal-cave.ogg", import.meta.url).href;
const MAP_BGM_REPLAY_HANDLER_KEY = Symbol("mapBgmReplayHandler");
const ALTER_CAVE_RECOVERY_MAP_ID = "Alter_Cave_B4";
const ALTER_CAVE_RECOVERY_GID = 36;
const ALTER_CAVE_RECOVERY_TEXT_INDEX = 582;
const UR_ELDER_HOUSE_1_MAP_ID = "Ur_ElderHouse_1";
const UR_ELDER_HOUSE_FULL_RECOVERY_SPRING = { x: 3, y: 9 };
const UR_ELDER_HOUSE_FULL_RECOVERY_TEXT_INDEX = 891;
const UR_ELDER_HOUSE_REVIVE_SPRING = { x: 21, y: 9 };
const UR_ELDER_HOUSE_REVIVE_TEXT_INDEX = 890;
const KAZUS_SHRINE_MAP_ID = "Kazus_Shrine";
const KAZUS_SHRINE_REVIVE_SPRING = { x: 3, y: 5 };
const UR_INN_ITEMSHOP_MAP_ID = "Ur_Inn_ItemShop";
const UR_INN_ITEMSHOP_RECOVERY_TILES = [
  { x: 7, y: 8 },
  { x: 9, y: 8 },
];
const KAZUS_INN_ITEMSHOP_2F_MAP_ID = "Kazus_Inn_ItemShop_2F";
const KAZUS_INN_ITEMSHOP_2F_RECOVERY_TILES = [
  { x: 4, y: 4 },
  { x: 6, y: 4 },
];
const AIRSHIP_OBTAINED_EVENT_FLAG = "cid_airship_obtained";
const AIRSHIP_DESTROYED_EVENT_FLAG = "cid_airship_destroyed";
const CANOE_OBTAINED_EVENT_FLAG = "canoe_obtained";
const AIRSHIP_OF_CID_MAP_ID = "Airship_of_Cid";
const AIRSHIP_OF_CID_HELM_TILE = { x: 23, y: 11 };
const AIRSHIP_FLOATING_CONTINENT_TILE = { x: 90, y: 59 };
const FLOATING_CONTINENT_BIG_ROCK_CRASH_TILE = { x: 82, y: 54 };
const CANOE_IMAGE_URL = new URL("../../assets/images/objects/canoe.png", import.meta.url).href;
const CANOE_SPRITE_COLUMNS = 4;
const CANOE_WATER_GIDS = new Set([9, 10, 25, 26, 59, 67]);
const AIRSHIP_BLOCKED_GIDS = new Set([7, 22, 23, 24, 39]);
const AIRSHIP_SPRITE_FRAMES = 8;
const AIRSHIP_IMAGE_URL = new URL("../../assets/images/objects/airship.png", import.meta.url).href;
const AIRSHIP_CRASH_DURATION_MS = 1400;
const FLOATING_CONTINENT_LOCATION_GROUP = "Floating Continent";
const FLOATING_CONTINENT_DEFAULT_LOCATION = "Floating Continent Near Ur";
const FLOATING_CONTINENT_SEA_LOCATION = "Floating Continent Seas";
const FLOATING_CONTINENT_DESERT_LOCATION = "Floating Continent Near desert";
const FLOATING_CONTINENT_SEA_GIDS = new Set([15, 30, 31, 32, 47]);
const FLOATING_CONTINENT_LOCATION_SPAWNS = {
  "Floating Continent Near Ur": { x: 95, y: 39 },
  "Floating Continent Near Castle Argus": { x: 53, y: 54 },
  "Floating Continent North of Gulgan Gulch": { x: 38, y: 44 },
  "Floating Continent Near Lake Dohr": { x: 25, y: 51 },
  "Floating Continent Seas": { x: 70, y: 74 },
  "Floating Continent Near desert": { x: 57, y: 84 },
};
const KAZUS_MAP_ID = "Kazus";
const CANAAN_MAP_ID = "Canaan";
const KAZUS_BLACKSMITH_MAP_ID = "Kazus_Blacksmith";
const KAZUS_NPC_516_KEY = "kazus_npc_516_scripted";
const KAZUS_CID_JOIN_KEY = "kazus_cid_join_scripted";
const KAZUS_CID_JOIN_SEQUENCE_ID = "kazus_cid_join";
const KAZUS_CID_FOLLOWER_EVENT_FLAG = "kazus_cid_follower_joined";
const CANAAN_CID_FAREWELL_SEQUENCE_ID = "canaan_cid_farewell";
const CANAAN_CID_FAREWELL_EVENT_FLAG = "canaan_cid_farewell_complete";
const KAZUS_BLACKSMITH_TAKA_KEY = "kazus_blacksmith_taka_scripted";
const KAZUS_BLACKSMITH_MITHRIL_RAM_EVENT_FLAG = "kazus_blacksmith_mythril_ram_complete";
const KAZUS_BLACKSMITH_TAKA_OUTBOUND_PATH = [
  { x: 5, y: 6 },
  { x: 5, y: 7 },
  { x: 5, y: 8 },
  { x: 5, y: 9 },
  { x: 6, y: 9 },
  { x: 6, y: 10 },
  { x: 6, y: 11 },
  { x: 6, y: 12 },
];
const KAZUS_BLACKSMITH_TAKA_RETURN_PATH = [
  { x: 6, y: 11 },
  { x: 6, y: 10 },
  { x: 6, y: 9 },
  { x: 5, y: 9 },
  { x: 5, y: 8 },
  { x: 5, y: 7 },
  { x: 5, y: 6 },
  { x: 6, y: 6 },
];
const KAZUS_CID_JOIN_PATH = [
  { x: 12, y: 20 },
  { x: 12, y: 21 },
  { x: 12, y: 22 },
  { x: 12, y: 23 },
  { x: 12, y: 24 },
  { x: 12, y: 25 },
  { x: 11, y: 25 },
  { x: 10, y: 25 },
  { x: 10, y: 26 },
  { x: 10, y: 27 },
  { x: 10, y: 28 },
  { x: 9, y: 28 },
];
const KAZUS_CID_FOLLOWER_START = { x: 9, y: 28, direction: "left" };
const CANAAN_CID_INITIAL_DESTINATION = { x: 16, y: 27 };
const CANAAN_CID_CROSSROAD_DESTINATION = { x: 15, y: 26 };
const CANAAN_CID_NORTH_DESTINATION = { x: 15, y: 23 };
const CANAAN_CID_EXIT_LANE_DESTINATION = { x: 14, y: 23 };
const CANAAN_CID_EXIT_FINAL_DESTINATION = { x: 14, y: 17 };
const SEALED_CAVE_B2_2_MAP_ID = "Sealed_Cave_B2_2";
const SEALED_CAVE_B3_MAP_ID = "Sealed_Cave_B3";
const SEALED_CAVE_B2_2_SARA_KEY = "sealed_cave_b2_2_sara_scripted";
const SEALED_CAVE_B2_2_SARA_EVENT_FLAG = "sealed_cave_b2_2_sara_escort_started";
const SEALED_CAVE_B3_DJINN_EVENT_FLAG = "sealed_cave_b3_djinn_event_complete";
const SEALED_CAVE_B3_DJINN_CUTSCENE_ID = "sealed_cave_b3_djinn";
const CASTLE_SASUNE_MAINKEEP_B1F_MAP_ID = "Castle_Sasune_MainKeep_B1F";
const CASTLE_SASUNE_MAINKEEP_POST_DJINN_ENTRY = {
  player: { x: 5, y: 5, direction: "left" },
  sara: { x: 5, y: 6, direction: "left" },
};
const CASTLE_SASUNE_MAINKEEP_RING_THROW = {
  start: { x: 5, y: 6 },
  end: { x: 2, y: 6 },
};
const CASTLE_SASUNE_MAINKEEP_4F_POST_DJINN_SPAWN = { x: 7, y: 11 };
const SEALED_CAVE_SARA_LEAVE_EVENT_FLAG = "sara_left_party";
const CASTLE_SASUNE_MAINKEEP_4F_KING_545_SPOKEN_FLAG = "castle_sasune_mainkeep_4f_king_545_spoken";
const SARA_FOLLOWER_DIALOGUE_SEQUENCE = [122, 123, 124, 125];
const CID_FOLLOWER_INITIAL_DIALOGUE_INDEX = 108;
const CID_FOLLOWER_RANDOM_DIALOGUE_INDICES = [109, 110, 112];
const SEALED_CAVE_B2_2_SARA_PATH = [
  { x: 3, y: 2 },
  { x: 3, y: 3 },
  { x: 3, y: 4 },
  { x: 4, y: 4 },
  { x: 5, y: 4 },
  { x: 6, y: 4 },
];
const SEALED_CAVE_B3_DJINN_PLAYER_PATH = [
  { x: 7, y: 23 },
  { x: 8, y: 23 },
  { x: 8, y: 22 },
];
const SEALED_CAVE_B3_DJINN_SARA_DESTINATION = { x: 8, y: 20 };
const CASTLE_SASUNE_MAINKEEP_1F_MAP_ID = "Castle_Sasune_MainKeep_1F";
const CASTLE_SASUNE_MAINKEEP_1F_RECOVERY_TILES = [
  { x: 1, y: 4 },
  { x: 3, y: 4 },
];
const CASTLE_SASUNE_TOWER_EAST_4F_MAP_ID = "Castle_Sasune_Tower_East_4F";
const CASTLE_SASUNE_TOWER_EAST_4F_RECOVERY_TILES = [
  { x: 4, y: 3 },
];
const CASTLE_SASUNE_MAINKEEP_4F_MAP_ID = "Castle_Sasune_MainKeep_4F";
const CASTLE_SASUNE_MAINKEEP_4F_SARA_DIALOGUE_TILE = { x: 7, y: 4 };
const CASTLE_SASUNE_MAINKEEP_4F_SARA_DIALOGUE_INDEX = 518;
const UR_INN_ITEMSHOP_RECOVERY_TEXT_INDEX = 223;
const CASTLE_SASUNE_TOWER_EAST_4F_RECOVERY_TEXT_INDEX = 130;
const ALTER_CAVE_CRYSTAL_ROOM_MAP_ID = "Alter_Cave_Crystal_Room";
const ALTER_CAVE_CRYSTAL_BOSS_NAME = "Land Turtle";
const ALTER_CAVE_CRYSTAL_OPENING_STORY_LINES = [
  "４にんは　ひかりのなかで\nそのいしを　そのこころを　かんじとり\nたびだつ　けついをした",
  "さあ　やみをふりはらい\nふたたび\nこのせかいに　ひかりをとりもどすのだ",
  "クリスタルのひかりを　きぼうにかえて…",
];
const MERGED_FIXED_DIALOGUE_PAGE_OVERRIDES = {
  538: [
    "しろのひとは　みんなジンの　のろいによって\nゆうれいのようなすがたに　されてしまいました。\nわたしは　つかいで　でていたので\nたすかったのです……",
    "ミスリルのゆびわがあれば　ジンをふたたび\nふういんできるのですが　ゆいいつ　ゆびわを\nつくれる　カズスのむらも　おなじような\nありさまで……\nいったい　わたしはどうしたらいいのか……",
  ],
  506: [
    "「わかっておる。　まさか　おまえたちが\n　えらばれるとは　かんがえもしなかった。",
    "　\\char1[0x02]　\\char2[0x02]\n　\\char3[0x02]　\\char4[0x02]……",
    "　これは　ぐうぜんの　せんたくではないことを\n　まず　しらなければならない。\n　クリスタルは　そのいしで　おまえたちを\n　えらんだのだ。",
    "　さあ　そのちからを……　おまえたちの\n　ひかりのこころを　むだにしてはならない。\n　たびだつのじゃ！\n　そして　やみのちからを　ふうじるのだ。",
  ],
  550: [
    "「わたしはサラ……　サスーンおうのむすめです。\n『サラひめ。　どうしてこんなところに？\n「わたしは　ミスリルのゆびわを　つけていたので\n　ジンの　のろいに　かからなかったのです。",
    "しろの　みんなを　たすけたくて　ここまで\nきたのだけれど　まものがいて　さきには\nすすめません……",
    "『ここは　きけんだ。\n　サラひめは　しろでまっていてください。\n「いいえ！いきます。\n　ひとりでもいくわ！！",
  ],
  551: [
    "『こまった　おひめさまだ……\n「おねがい　いっしょにつれていって！\n　この　ミスリルのゆびわがなければ　ジンを\n　ふういんすることはできません！",
    "『しかたがないな……\nサラひめが　パーティーにくわわった！",
  ],
  532: [
    "わしはシド。　カナーンからきたんじゃ。\nネルブのたにが　おおいわでふさがれてしまい\nカナーンに　かえるにかえれなくなってしまった。\nそこでこのまちに　ひとばんの　やどを",
    "もとめたのじゃが　このざまじゃ。　フォフォフォ！\nどうだわかいの　わしの　ひくうていを　かして\nやるから　なんとかしてくれんかのう？\nにしのさばくにかくしてあるんじゃ。",
    "シドから　ひくうていを　かくしたばしょを\nきいた！\nにしの　さばくだ！！",
  ],
  544: [
    "「わたしはサスーンのおう。　ジンの　のろいに\nよって　みな　ゆうれいのようなすがたに\nかえられてしまった。　ジンを　たおさぬかぎり\nもとの　すがたには　もどれぬ。",
    "『ジンはどこに？\n「しろのきたにある　ふういんのどうくつにいる。\nだが　ミスリルのゆびわが　なければ\nジンを　ふたたび　ふういんすることはできぬ。\n『サラひめが　もっていると……\n「おお　そうだ！　むかし　カズスより　サラひめに\nミスリルのゆびわが　おくられた。　だが\nかんじんの　サラが　どこにもみあたらん。\nもしや　ジンにさらわれたのでは？！\nおお　サラひめ……",
    "『ふういんのどうくつに　いってみましょう。\n「おお　せんしたちよ　よくぞいってくれた。\nたしか　ふういんのどうくつには　１かしょ\nかくしとびらが　ある。　がいこつが　かぎに\nなっていたはずだ……",
    "たのむ！\nジンをたおし　ひとびとをすくってくれ！！",
  ],
  518: [
    "おう「おお　サラひめ！　ぶじだったか！\nサラ「まっていてね。　わたしのこのゆびわで\n　　　ジンを　ふういんします！\nおう「しんぱいじゃ……",
    "サラ「だいじょうぶよ！\n　　　\\xcharたちが　ついてるもの。　ねっ！",
  ],
  545: [
    "ありがとう　せんしたちよ。\nふたたび　ジンをふういんし\nサラひめを　たすけだしてくれたこと\nれいをいう。",
    "これを　もっていくといい。\nなにかのやくにたつかもしれん。\n\nおうさまから　カヌーをもらった！",
  ],
  546: [
    "サラ「わたしは　おとうさまの　そばについて\nいなくてはなりません。\nほんとうは　あなたについていきたい……\nでもきっと　あしでまといになってしまいますね……",
    "『サラひめ……\n「たびが　おわったら　かならず　かえってきて\nくださいね。\nわたし　まっています。",
  ],
  12: [
    "なにも　おこらない。\nジン「ファファファ……　いまの　おれさまには\nそんなもの　つうようしないわ。\nぞうだいした　やみのちからが　おれに",
    "みかたしているのだ！\nジンがおそってきた！",
  ],
  14: [
    "ジンは　きりのように　とけてきえた。\nゆびわの　ちからによって　ふたたび　どうくつの\nおくへと　ふういんされたのだ。",
    "「ありがとうございます。\nあなたがたのおかげで　ジンを　ふたたび\nふういんすることができました。",
    "あとは　このゆびわを　サスーンじょうの\nせいなるいずみにつければ　ジンの　のろいを\nとくことができます。　ゆびわのちからで\nサスーンじょうまで　ワープしましょう！",
  ],
  15: [
    "サラひめは　ゆびわを　いずみになげた。\n「さあ　これでジンの　のろいは　とけたはずです。\nありがとう。　あなたがたの　おかげだわ。\nおわかれですね……わたしは　おとうさまの",
    "そばにいなくてはなりません。\nほんとうは　ついていきたい……\nでもきっと　あしでまといに　なってしまいますね\n『サラ……",
    "「たびが　おわったら　かならず　かえってきて\nくださいね。　わたし　まっています。\nいつまでも……\nサラと　わかれた……",
  ],
  16: [
    "よくやった！\nさすが　わしが　みこんだだけのことはあるわい。\nひくうていは　おまえさんたちが　やくにたてるのが\n１ばんいいじゃろう。",
    "それより　わしを　ばあさんのまつ　カナーンの\nむらまで　つれていってくれ。\nなっ　たのむ！\nシドじいさんが　パーティーにくわわった。",
  ],
  17: [
    "ありがとうよ。\nわしのできることなら　なんでもいってくれ……\nそうだ！　もう１ど　ひくうていをつくれれば\nおまえさんたちの　やくにたつかもしれんな。",
    "アーガスおうに　あうのじゃ！\nおうが　ひくうていの　ひみつを　しっている。\nほんとに　たすかったよ！\nいつでもまた　きなさい！",
  ],
  562: [
    "デッシュとかいったかね……\nあのろくでなしに　むすめの　サリーナは\nぞっこんなんだよ。\nまいったね……",
    "あのおとこ　どうしても　さがさなければならない\nものが　あるといって　たびにでちまった。\nおかげで　むすめは　ないてばかりさ。",
  ],
  563: [
    "サリーナ「ああ……デッシュさま。\nこんなに　おしたいしておりますのに……\nシクシク……",
    "りゅうが　すむという　みなみのやまに\nいってしまわれました……",
  ],
  535: [
    "シド「カナーンへいくために\n　　　ネルブのおおいわを　くだこうとおもうのだが……\n　　　ひくうていにミスリルせいの　せんしゅを\n　　　つければなんとかなるかもしれん。",
    "タカ「よーしまっておれ！　いま　つくってやる！！",
  ],
  536: [
    "そーれ　おわったぞい！\nなーに　れいはいらんよ。　むらを　すくって\nくれたんじゃからの。　あたりまえじゃ。\nそれでは　きをつけていきなされ！",
    "タカじいさんが　ひくうていに\nミスリルのせんしゅを　つけてくれた！\nシド「よーし　ひくうていで　おおいわに\n　　　たいあたりじゃ！！",
  ],
};
const MAP_SHOP_ACTIVATIONS = [
  { mapId: "Ur_ArmorShop", x: 3, y: 5, shopMap: "Ur", shopType: "Armor" },
  { mapId: "Ur_MagicShop", x: 4, y: 4, shopMap: "Ur", shopType: "Magic" },
  { mapId: "Ur_WeaponShop", x: 3, y: 4, shopMap: "Ur", shopType: "Weapons" },
  { mapId: "Ur_Inn_ItemShop", x: 8, y: 15, shopMap: "Ur", shopType: "Items" },
  { mapId: "Kazus_ArmorShop", x: 3, y: 5, shopMap: "Kazus", shopType: "Armor" },
  { mapId: "Kazus_MagicShop", x: 4, y: 4, shopMap: "Kazus", shopType: "Magic" },
  { mapId: "Kazus_WeaponShop", x: 3, y: 4, shopMap: "Kazus", shopType: "Weapons" },
  { mapId: "Kazus_Inn_ItemShop_1F", x: 13, y: 6, shopMap: "Kazus", shopType: "Items" },
  { mapId: "Canaan_ArmorShop", x: 3, y: 5, shopMap: "Canaan", shopType: "Armor" },
  { mapId: "Canaan_Inn_ItemShop", x: 11, y: 5, shopMap: "Canaan", shopType: "Items" },
  { mapId: "Canaan_MagicShop", x: 4, y: 4, shopMap: "Canaan", shopType: "Magic" },
  { mapId: "Canaan_WeaponShop", x: 3, y: 4, shopMap: "Canaan", shopType: "Weapons" },
];
const CRYSTAL_SPRITE_FRAMES = 4;
const CRYSTAL_SPRITE_FRAME_MS = 500;
const CRYSTAL_IMAGE_URL = new URL("../../assets/images/objects/crystal.png", import.meta.url).href;
const ONION_KNIGHT_IMAGE_URL = new URL("../../assets/images/characters/fs_onion_knight.png", import.meta.url).href;
const ONION_KNIGHT_CHARACTER_SPRITE = {
  rows: 4,
  url: ONION_KNIGHT_IMAGE_URL,
};
function buildFieldCharacterSprite(jobKey) {
  const fileKey = String(jobKey || "").replace(/-/g, "_");
  return {
    rows: 1,
    url: new URL(`../../assets/images/characters/fs_${fileKey}.png`, import.meta.url).href,
  };
}

const CHARACTER_SPRITES_BY_JOB_KEY = {
  bard: buildFieldCharacterSprite("bard"),
  "black-belt": buildFieldCharacterSprite("black-belt"),
  "black-mage": buildFieldCharacterSprite("black-mage"),
  devout: buildFieldCharacterSprite("devout"),
  dragoon: buildFieldCharacterSprite("dragoon"),
  evoker: buildFieldCharacterSprite("evoker"),
  geomancer: buildFieldCharacterSprite("geomancer"),
  knight: buildFieldCharacterSprite("knight"),
  magus: buildFieldCharacterSprite("magus"),
  monk: buildFieldCharacterSprite("monk"),
  "mystic-knight": buildFieldCharacterSprite("mystic-knight"),
  ninja: buildFieldCharacterSprite("ninja"),
  "onion-knight": ONION_KNIGHT_CHARACTER_SPRITE,
  ranger: buildFieldCharacterSprite("ranger"),
  "red-mage": buildFieldCharacterSprite("red-mage"),
  sage: buildFieldCharacterSprite("sage"),
  scholar: buildFieldCharacterSprite("scholar"),
  summoner: buildFieldCharacterSprite("summoner"),
  thief: buildFieldCharacterSprite("thief"),
  viking: buildFieldCharacterSprite("viking"),
  warrior: buildFieldCharacterSprite("warrior"),
  "white-mage": buildFieldCharacterSprite("white-mage"),
};
let inventoryResolverDataPromise = null;
let mergedFixedContentPromise = null;
const mapRenderStateCache = new WeakMap();
const waterHighlightMaskCache = new Map();
const waterFlowTileCache = new Map();
let activeAirshipCrashAnimationFrameId = null;

export function isFloatingContinentMap(mapDefinition) {
  return String(mapDefinition?.id || "") === FLOATING_CONTINENT_MAP_ID;
}

function isFloatingContinentKnownLocation(locationName) {
  return Object.prototype.hasOwnProperty.call(
    FLOATING_CONTINENT_LOCATION_SPAWNS,
    String(locationName || ""),
  );
}

export function resolveFloatingContinentSpawn(locationName, fallbackSpawn = null) {
  const normalizedLocation = String(locationName || "");
  const spawn = FLOATING_CONTINENT_LOCATION_SPAWNS[normalizedLocation];
  if (spawn) {
    return { x: Number(spawn.x), y: Number(spawn.y) };
  }
  return {
    x: Number(
      fallbackSpawn?.x
      ?? FLOATING_CONTINENT_LOCATION_SPAWNS[FLOATING_CONTINENT_DEFAULT_LOCATION].x,
    ),
    y: Number(
      fallbackSpawn?.y
      ?? FLOATING_CONTINENT_LOCATION_SPAWNS[FLOATING_CONTINENT_DEFAULT_LOCATION].y,
    ),
  };
}

function isWithinFloatingContinentRect(position, bounds) {
  const x = Number(position?.tile_x ?? position?.x);
  const y = Number(position?.tile_y ?? position?.y);
  return (
    Number.isFinite(x)
    && Number.isFinite(y)
    && x >= bounds.xMin
    && x <= bounds.xMax
    && y >= bounds.yMin
    && y <= bounds.yMax
  );
}

export function resolveFloatingContinentLocationFromPosition(
  mapDefinition,
  position,
  saveEnvelope = null,
) {
  if (!isFloatingContinentMap(mapDefinition)) return "";
  const x = Number(position?.tile_x ?? position?.x);
  const y = Number(position?.tile_y ?? position?.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return "";
  const gid = Number(mapDefinition?.rows?.[y]?.[x] ?? NaN);
  if (FLOATING_CONTINENT_SEA_GIDS.has(gid)) {
    return FLOATING_CONTINENT_SEA_LOCATION;
  }
  if (isWithinFloatingContinentRect(position, { xMin: 69, xMax: 104, yMin: 28, yMax: 99 })) {
    return FLOATING_CONTINENT_DEFAULT_LOCATION;
  }
  if (isWithinFloatingContinentRect(position, { xMin: 45, xMax: 66, yMin: 29, yMax: 61 })) {
    return "Floating Continent Near Castle Argus";
  }
  if (isWithinFloatingContinentRect(position, { xMin: 32, xMax: 44, yMin: 19, yMax: 44 })) {
    return "Floating Continent North of Gulgan Gulch";
  }
  if (isWithinFloatingContinentRect(position, { xMin: 23, xMax: 41, yMin: 45, yMax: 63 })) {
    return "Floating Continent Near Lake Dohr";
  }
  if (canOccupyTile(mapDefinition, x, y, saveEnvelope)) {
    return FLOATING_CONTINENT_DESERT_LOCATION;
  }
  return "";
}

function resolveFloatingContinentSelection(
  mapDefinition,
  fallbackSelection = {},
  position = null,
  saveEnvelope = null,
) {
  if (!isFloatingContinentMap(mapDefinition)) {
    return {
      selected_location_group: String(
        fallbackSelection?.selected_location_group
        || fallbackSelection?.selectedLocationGroup
        || "",
      ),
      selected_location: String(
        fallbackSelection?.selected_location
        || fallbackSelection?.selectedLocation
        || "",
      ),
    };
  }
  const resolvedLocation = resolveFloatingContinentLocationFromPosition(
    mapDefinition,
    position,
    saveEnvelope,
  );
  if (resolvedLocation) {
    return {
      selected_location_group: FLOATING_CONTINENT_LOCATION_GROUP,
      selected_location: resolvedLocation,
    };
  }
  const fallbackLocation = String(
    fallbackSelection?.selected_location
    || fallbackSelection?.selectedLocation
    || "",
  );
  return {
    selected_location_group: FLOATING_CONTINENT_LOCATION_GROUP,
    selected_location: isFloatingContinentKnownLocation(fallbackLocation)
      ? fallbackLocation
      : FLOATING_CONTINENT_DEFAULT_LOCATION,
  };
}

function resolveFloatingContinentFreshAirshipState(selectedLocation, saveEnvelope = null) {
  if (
    !isSavedEventFlagEnabled(saveEnvelope, AIRSHIP_OBTAINED_EVENT_FLAG)
    || isSavedEventFlagEnabled(saveEnvelope, AIRSHIP_DESTROYED_EVENT_FLAG)
  ) {
    return {};
  }
  const spawn = resolveFloatingContinentSpawn(selectedLocation, AIRSHIP_FLOATING_CONTINENT_TILE);
  const isSeaSpawn = String(selectedLocation || "") === FLOATING_CONTINENT_SEA_LOCATION;
  return {
    airship_riding: isSeaSpawn,
    airship_tile_x: isSeaSpawn ? spawn.x : spawn.x - 1,
    airship_tile_y: spawn.y,
  };
}

function resolveEncounterSelectionForMapState(
  mapDefinition,
  fallbackSelection = {},
  mapState = null,
  saveEnvelope = null,
) {
  if (isFloatingContinentMap(mapDefinition)) {
    return resolveFloatingContinentSelection(
      mapDefinition,
      fallbackSelection,
      mapState,
      saveEnvelope,
    );
  }
  return buildEncounterSelection(mapDefinition, fallbackSelection);
}

export function resolveMapBgmUrl(mapDefinition, fallbackSelection = {}) {
  const mapId = String(mapDefinition?.id || "");
  if (mapId === FLOATING_CONTINENT_MAP_ID) {
    return FLOATING_CONTINENT_BGM_URL;
  }
  const locationGroup = String(
    mapDefinition?.locationRequirement?.group
    || fallbackSelection?.selected_location_group
    || fallbackSelection?.selectedLocationGroup
    || "",
  );
  if (locationGroup === "Ur") {
    return UR_BGM_URL;
  }
  if (locationGroup === "Kazus") {
    return KAZUS_BGM_URL;
  }
  if (locationGroup === "Alter Cave" || locationGroup === "Altar Cave") {
    return ALTER_CAVE_BGM_URL;
  }
  return "";
}

export function configureLoopingMapBgm(audioElement, sourceUrl = FLOATING_CONTINENT_BGM_URL) {
  if (!audioElement) return null;
  audioElement.src = String(sourceUrl || "");
  audioElement.loop = false;
  audioElement.preload = "metadata";
  try {
    audioElement.playsInline = true;
    audioElement.setAttribute?.("playsinline", "true");
    audioElement.setAttribute?.("webkit-playsinline", "true");
  } catch (_error) {
    // Ignore browsers that do not expose inline playback flags on Audio.
  }
  if (!audioElement[MAP_BGM_REPLAY_HANDLER_KEY] && typeof audioElement.addEventListener === "function") {
    const replayHandler = () => {
      try {
        audioElement.currentTime = 0;
        const playResult = audioElement.play?.();
        if (playResult && typeof playResult.catch === "function") {
          playResult.catch(() => {});
        }
      } catch (_error) {
        // Ignore replay failures; the next explicit sync will retry playback.
      }
    };
    audioElement.addEventListener("ended", replayHandler);
    audioElement[MAP_BGM_REPLAY_HANDLER_KEY] = replayHandler;
  }
  return audioElement;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function interpolateMapPosition(fromPosition, toPosition, progress) {
  const startX = asNumber(fromPosition?.x, 0);
  const startY = asNumber(fromPosition?.y, 0);
  const endX = asNumber(toPosition?.x, startX);
  const endY = asNumber(toPosition?.y, startY);
  const clampedProgress = clamp(asNumber(progress, 0), 0, 1);
  return {
    x: startX + (endX - startX) * clampedProgress,
    y: startY + (endY - startY) * clampedProgress,
  };
}

export function resolveMapVisualPosition(visualPosition, fallbackPosition = {}) {
  return {
    x: asNumber(visualPosition?.x, fallbackPosition?.x),
    y: asNumber(visualPosition?.y, fallbackPosition?.y),
  };
}

export function resolveCharacterSpriteFrame(direction, walkFrame = 0) {
  const normalizedDirection = String(direction || "down");
  const frameOffset = Math.abs(Number(walkFrame || 0)) % 2;
  const baseFrame = {
    up: 0,
    left: 2,
    right: 2,
    down: 4,
  }[normalizedDirection] ?? 4;
  return {
    frameIndex: baseFrame + frameOffset,
    facingScale: normalizedDirection === "right" ? -1 : 1,
  };
}

export function resolveNpcSpriteFrame(direction, walkFrame = 0) {
  const normalizedDirection = NPC_DIRECTIONS.includes(String(direction || ""))
    ? String(direction)
    : "down";
  const frameOffset = Math.abs(Number(walkFrame || 0)) % 2;
  const baseFrame = {
    up: 0,
    left: 2,
    right: 2,
    down: 4,
  }[normalizedDirection] ?? 4;
  return baseFrame + frameOffset;
}

export function resolveNpcFacingScale(direction) {
  return String(direction || "") === "right" ? -1 : 1;
}

export function chooseNextNpcDirection(currentDirection, randomValue = Math.random()) {
  const current = String(currentDirection || "");
  const candidates = NPC_DIRECTIONS.filter((direction) => direction !== current);
  const rows = candidates.length ? candidates : NPC_DIRECTIONS;
  const index = clamp(Math.floor(Number(randomValue || 0) * rows.length), 0, rows.length - 1);
  return rows[index] || "down";
}

export function resolveSaraFollowerDialogueIndex(dialogueCount = 0, randomValue = Math.random()) {
  const normalizedCount = Math.max(0, Math.floor(Number(dialogueCount || 0)));
  if (normalizedCount < SARA_FOLLOWER_DIALOGUE_SEQUENCE.length) {
    return SARA_FOLLOWER_DIALOGUE_SEQUENCE[normalizedCount];
  }
  const fallbackSequence = SARA_FOLLOWER_DIALOGUE_SEQUENCE.slice(1);
  const normalizedRandom = clamp(Number(randomValue || 0), 0, 0.999999999);
  const index = Math.floor(normalizedRandom * fallbackSequence.length);
  return fallbackSequence[index] || fallbackSequence[0];
}

export function resolveCidFollowerDialogueIndex(
  dialogueCount = 0,
  randomValue = Math.random(),
  hasKazusBlacksmithRamUpgrade = false,
) {
  const normalizedCount = Math.max(0, Math.floor(Number(dialogueCount || 0)));
  if (normalizedCount === 0) {
    return CID_FOLLOWER_INITIAL_DIALOGUE_INDEX;
  }
  if (hasKazusBlacksmithRamUpgrade) {
    return 112;
  }
  const normalizedRandom = clamp(Number(randomValue || 0), 0, 0.999999999);
  const index = Math.floor(normalizedRandom * CID_FOLLOWER_RANDOM_DIALOGUE_INDICES.length);
  return CID_FOLLOWER_RANDOM_DIALOGUE_INDICES[index] || CID_FOLLOWER_RANDOM_DIALOGUE_INDICES[0];
}

export function normalizeNpcDirection(direction, fallback = "down") {
  const normalizedDirection = String(direction || "").trim().toLowerCase();
  return NPC_DIRECTIONS.includes(normalizedDirection) ? normalizedDirection : fallback;
}

export function normalizeMapFacingDirection(direction, fallback = "down") {
  const normalizedDirection = String(direction || "").trim().toLowerCase();
  return NPC_DIRECTIONS.includes(normalizedDirection) ? normalizedDirection : fallback;
}

export function normalizeNpcMovement(movement) {
  const normalizedMovement = String(movement || "").trim().toLowerCase();
  return normalizedMovement === NPC_MOVEMENT_RANDOM ? NPC_MOVEMENT_RANDOM : "fixed";
}

export function resolveNpcInitialDirection(row, randomValue = Math.random()) {
  const configuredDirection = normalizeNpcDirection(row?.direction, "");
  if (configuredDirection) return configuredDirection;
  return chooseNextNpcDirection("", randomValue);
}

export function resolveNpcNextDirectionDelay(randomValue = Math.random()) {
  const normalized = clamp(Number(randomValue || 0), 0, 1);
  return NPC_DIRECTION_MIN_MS + Math.floor((NPC_DIRECTION_MAX_MS - NPC_DIRECTION_MIN_MS) * normalized);
}

export function normalizeCharacterJobKey(jobName) {
  return String(jobName || "")
    .trim()
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function firstPartyMemberFromAppState(appState) {
  const menuParty = Array.isArray(appState?.menuState?.party) ? appState.menuState.party : [];
  if (menuParty[0] && typeof menuParty[0] === "object") return menuParty[0];
  const saveParty = Array.isArray(appState?.saveEnvelope?.save?.party) ? appState.saveEnvelope.save.party : [];
  if (saveParty[0] && typeof saveParty[0] === "object") return saveParty[0];
  return null;
}

export function resolveLeaderCharacterSprite(appState) {
  const leader = firstPartyMemberFromAppState(appState);
  const jobKey = normalizeCharacterJobKey(
    leader?.current_job
    || leader?.job
    || leader?.job_name,
  );
  return CHARACTER_SPRITES_BY_JOB_KEY[jobKey] || ONION_KNIGHT_CHARACTER_SPRITE;
}

export function resolveLeaderCharacterSpriteUrl(appState) {
  return resolveLeaderCharacterSprite(appState).url;
}

export function createDirectionalHoldRepeater(
  runStep,
  scheduler = globalThis,
  options = {},
) {
  const initialDelay = Math.max(0, Number(options.initialDelay ?? HOLD_MOVE_INITIAL_DELAY_MS));
  const repeatInterval = Math.max(1, Number(options.repeatInterval ?? HOLD_MOVE_REPEAT_MS));
  let timeoutId = null;
  let intervalId = null;
  let activeDirection = "";

  function clearTimers() {
    if (timeoutId !== null) {
      scheduler.clearTimeout(timeoutId);
      timeoutId = null;
    }
    if (intervalId !== null) {
      scheduler.clearInterval(intervalId);
      intervalId = null;
    }
  }

  function stop(direction = "") {
    if (direction && direction !== activeDirection) return false;
    const hadActiveDirection = Boolean(activeDirection);
    activeDirection = "";
    clearTimers();
    return hadActiveDirection;
  }

  function start(direction) {
    const normalizedDirection = String(direction || "");
    if (!normalizedDirection) return false;
    if (normalizedDirection === activeDirection) return false;
    stop();
    activeDirection = normalizedDirection;
    void runStep(normalizedDirection);
    timeoutId = scheduler.setTimeout(() => {
      if (activeDirection !== normalizedDirection) return;
      intervalId = scheduler.setInterval(() => {
        if (activeDirection !== normalizedDirection) return;
        void runStep(normalizedDirection);
      }, repeatInterval);
    }, initialDelay);
    return true;
  }

  return {
    start,
    stop,
    isActive(direction = "") {
      return direction ? activeDirection === direction : Boolean(activeDirection);
    },
  };
}

function asNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function optionalNumber(value, fallback = null) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function normalizeMovementPlane(value, fallback = "ground") {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "ground" || normalized === "bridge") {
    return normalized;
  }
  return String(fallback || "ground").trim().toLowerCase() === "bridge" ? "bridge" : "ground";
}

export function npcDialogueIndices(row) {
  const rawIndices = Array.isArray(row?.dialogue_indices)
    ? row.dialogue_indices
    : [row?.dialogue_index];
  return rawIndices
    .map((index) => Number(index))
    .filter((index) => Number.isFinite(index));
}

export function resolveNpcDialogueIndicesForInteraction(mapDefinition, row, saveEnvelope = null) {
  if (
    String(mapDefinition?.id || "") === CASTLE_SASUNE_MAINKEEP_4F_MAP_ID
    && Number(row?.x) === CASTLE_SASUNE_MAINKEEP_4F_SARA_DIALOGUE_TILE.x
    && Number(row?.y) === CASTLE_SASUNE_MAINKEEP_4F_SARA_DIALOGUE_TILE.y
    && isSavedEventFlagEnabled(saveEnvelope, SEALED_CAVE_B2_2_SARA_EVENT_FLAG)
    && !isSavedEventFlagEnabled(saveEnvelope, SEALED_CAVE_SARA_LEAVE_EVENT_FLAG)
  ) {
    return [CASTLE_SASUNE_MAINKEEP_4F_SARA_DIALOGUE_INDEX];
  }
  return npcDialogueIndices(row);
}

function eventPostVictoryDialogueIndices(row) {
  const rawIndices = Array.isArray(row?.post_victory_dialogue_indices)
    ? row.post_victory_dialogue_indices
    : [row?.post_victory_dialogue_index];
  return rawIndices
    .map((index) => Number(index))
    .filter((index) => Number.isFinite(index));
}

function eventEnemyNames(row) {
  return Array.isArray(row?.enemy_names)
    ? row.enemy_names.map((name) => String(name || "")).filter((name) => Boolean(name))
    : [];
}

function normalizeSwitchStates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, enabled]) => [String(key || ""), Boolean(enabled)])
      .filter(([key]) => Boolean(key)),
  );
}

function normalizeTreasureStates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, opened]) => [String(key || ""), Boolean(opened)])
      .filter(([key]) => Boolean(key)),
  );
}

function treasureKey(row) {
  return String(row?.treasure_id || row?.name || `${row?.x},${row?.y}`);
}

function normalizeGuardedEnemyNames(value) {
  if (Array.isArray(value)) {
    return value.map((name) => String(name || "").trim()).filter(Boolean);
  }
  const single = String(value || "").trim();
  return single ? [single] : [];
}

function normalizeEventFlagStates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, enabled]) => [String(key || ""), Boolean(enabled)])
      .filter(([key]) => Boolean(key)),
  );
}

function readSavedEventFlags(saveEnvelope) {
  return normalizeEventFlagStates(saveEnvelope?.save?.event_flag);
}

function isSavedEventFlagEnabled(saveEnvelope, flagKey) {
  if (!flagKey) return false;
  return Boolean(readSavedEventFlags(saveEnvelope)[String(flagKey)]);
}

function writeSavedEventFlag(saveEnvelope, flagKey, enabled = true) {
  if (!flagKey) return saveEnvelope;
  const targetEnvelope = saveEnvelope && typeof saveEnvelope === "object" ? saveEnvelope : {};
  if (!targetEnvelope.save || typeof targetEnvelope.save !== "object") {
    targetEnvelope.save = {};
  }
  const currentFlags = readSavedEventFlags(targetEnvelope);
  targetEnvelope.save.event_flag = {
    ...currentFlags,
    [String(flagKey)]: Boolean(enabled),
  };
  return targetEnvelope;
}

function isMapObjectEventFlagSatisfied(row, saveEnvelope) {
  const requiredFlag = String(row?.required_event_flag || "");
  const requiredAbsentFlag = String(row?.required_event_flag_absent || "");
  if (requiredFlag && !isSavedEventFlagEnabled(saveEnvelope, requiredFlag)) return false;
  if (requiredAbsentFlag && isSavedEventFlagEnabled(saveEnvelope, requiredAbsentFlag)) return false;
  return true;
}

export function isMapObjectAvailable(row, saveEnvelope = null) {
  if (!row || typeof row !== "object") return false;
  return isMapObjectEventFlagSatisfied(row, saveEnvelope);
}

function isMapObjectRenderable(row, saveEnvelope = null) {
  return isMapObjectAvailable(row, saveEnvelope) && row?.hidden !== true;
}

function renderableMapObjects(mapDefinition, saveEnvelope = null) {
  return (mapDefinition?.objects || []).filter((row) => isMapObjectRenderable(row, saveEnvelope));
}

function readSavedTreasureStates(saveEnvelope, mapId) {
  const treasures = saveEnvelope?.save?.treasures;
  if (!treasures || typeof treasures !== "object" || Array.isArray(treasures)) return {};
  return normalizeTreasureStates(treasures[String(mapId || "")]);
}

function mergeTreasureStates(...values) {
  return values.reduce((merged, value) => {
    const normalized = normalizeTreasureStates(value);
    Object.entries(normalized).forEach(([key, opened]) => {
      if (opened) merged[key] = true;
    });
    return merged;
  }, {});
}

function writeSavedTreasureStates(saveEnvelope, mapId, openedTreasures) {
  const targetEnvelope = saveEnvelope && typeof saveEnvelope === "object" ? saveEnvelope : {};
  if (!targetEnvelope.save || typeof targetEnvelope.save !== "object") {
    targetEnvelope.save = {};
  }
  const currentTreasures = targetEnvelope.save.treasures;
  const nextTreasures = (
    currentTreasures && typeof currentTreasures === "object" && !Array.isArray(currentTreasures)
      ? { ...currentTreasures }
      : {}
  );
  const mapKey = String(mapId || "");
  const mergedForMap = mergeTreasureStates(nextTreasures[mapKey], openedTreasures);
  nextTreasures[mapKey] = mergedForMap;
  targetEnvelope.save.treasures = nextTreasures;
  return targetEnvelope;
}

function findTreasureByKey(mapDefinition, key) {
  const normalizedKey = String(key || "");
  return (mapDefinition?.objects || []).find((row) => (
    row?.type === "treasure" && treasureKey(row) === normalizedKey
  )) || null;
}

function addItemToInventory(save, bucketName, itemName, quantity = 1, spellLevelByName = {}) {
  if (!save || typeof save !== "object") return false;
  if (!save.inventory || typeof save.inventory !== "object") {
    save.inventory = {};
  }
  if (bucketName === "Magic") {
    const spellLevel = asNumber(spellLevelByName[itemName], 0);
    if (spellLevel <= 0) return false;
    const levelKey = `LV${spellLevel}`;
    if (!save.inventory.Magic || typeof save.inventory.Magic !== "object") {
      save.inventory.Magic = {};
    }
    if (!save.inventory.Magic[levelKey] || typeof save.inventory.Magic[levelKey] !== "object") {
      save.inventory.Magic[levelKey] = {};
    }
    const current = asNumber(save.inventory.Magic[levelKey][itemName], 0);
    save.inventory.Magic[levelKey][itemName] = current + quantity;
    return true;
  }
  if (!save.inventory[bucketName] || typeof save.inventory[bucketName] !== "object") {
    save.inventory[bucketName] = {};
  }
  const current = asNumber(save.inventory[bucketName][itemName], 0);
  save.inventory[bucketName][itemName] = current + quantity;
  return true;
}

async function loadSpellLevelByName() {
  if (!inventoryResolverDataPromise) {
    inventoryResolverDataPromise = Promise.all([
      loadJson("../assets/data/ffiii_items.json"),
      loadJson("../assets/data/ffiii_weapons.json"),
      loadJson("../assets/data/ffiii_armors.json"),
      loadJson("../assets/data/ffiii_spells.json"),
    ])
      .then(([itemsPayload, weaponsPayload, armorsPayload, spellsPayload]) => {
        const itemTypeByName = {};
        asArray(itemsPayload?.items).forEach((item) => {
          const name = String(item?.name || item?.Name || "");
          if (!name) return;
          itemTypeByName[name] = String(item?.ItemType || "");
        });
        return {
          itemTypeByName,
          weaponNameSet: new Set(asArray(weaponsPayload?.weapons).map((row) => String(row?.name || "")).filter(Boolean)),
          armorNameSet: new Set(asArray(armorsPayload?.armors).map((row) => String(row?.name || "")).filter(Boolean)),
          spellLevelByName: buildSpellLevelByName(spellsPayload),
        };
      })
      .catch((error) => {
        inventoryResolverDataPromise = null;
        throw error;
      });
  }
  return inventoryResolverDataPromise;
}

async function loadMergedFixedContentByIndex(index) {
  return loadMergedFixedContentByIndexWithCharacterName(index);
}

function normalizeDialogueCharacterName(characterName) {
  const normalized = String(characterName || "").trim();
  return normalized || "\\xchar";
}

function normalizeDialoguePartyMembers(partyMembers = []) {
  return Array.isArray(partyMembers) ? partyMembers.slice(0, 4) : [];
}

function resolveDialogueCharacterDisplayName(memberOrName) {
  if (memberOrName && typeof memberOrName === "object") {
    return String(memberOrName.name || "").trim();
  }
  return String(memberOrName || "").trim();
}

function resolveDialogueCharacterJobName(memberOrName) {
  if (!memberOrName || typeof memberOrName !== "object") return "";
  return String(
    memberOrName.current_job
    || memberOrName.job
    || memberOrName.job_name
    || "",
  ).trim();
}

function resolveDialogueCharacterTokenValue(partyMembers, index, typeCode) {
  const members = normalizeDialoguePartyMembers(partyMembers);
  const member = members[index];
  if (String(typeCode || "") === "0x01") {
    const jobName = resolveDialogueCharacterJobName(member);
    return jobName || `\\char${index + 1}[0x01]`;
  }
  const characterName = resolveDialogueCharacterDisplayName(member);
  return characterName || `\\char${index + 1}[0x02]`;
}

export function applyDialogueCharacterName(rawContent, partyMembers = []) {
  const members = normalizeDialoguePartyMembers(partyMembers);
  const leadReplacement = normalizeDialogueCharacterName(
    resolveDialogueCharacterDisplayName(members[0]),
  );
  return String(rawContent || "")
    .replace(/\\xchar/g, leadReplacement)
    .replace(/\\char([1-4])\[(0x01|0x02)\]/g, (_match, numberText, typeCode) => (
      resolveDialogueCharacterTokenValue(members, Number(numberText) - 1, typeCode)
    ));
}

async function loadMergedFixedContentByIndexWithCharacterName(index, partyMembers = []) {
  if (!mergedFixedContentPromise) {
    mergedFixedContentPromise = loadJson("../assets/data/merged_fixed.json")
      .catch((error) => {
        mergedFixedContentPromise = null;
        throw error;
      });
  }
  const rows = await mergedFixedContentPromise;
  const hit = Array.isArray(rows)
    ? rows.find((row) => Number(row?.index) === Number(index))
    : null;
  return normalizeMergedFixedContent(
    applyDialogueCharacterName(hit?.content ?? hit?.sontent ?? "", partyMembers),
  );
}

export function buildMergedFixedContentPages(index, rawContent, partyMembers = []) {
  const normalizedIndex = Number(index);
  const overridePages = MERGED_FIXED_DIALOGUE_PAGE_OVERRIDES[normalizedIndex];
  if (Array.isArray(overridePages) && overridePages.length > 0) {
    return overridePages
      .map((page) => normalizeMergedFixedContent(applyDialogueCharacterName(page, partyMembers)))
      .filter(Boolean);
  }
  const normalized = normalizeMergedFixedContent(applyDialogueCharacterName(rawContent, partyMembers));
  return normalized ? [normalized] : [];
}

async function loadMergedFixedContentByIndices(indices, partyMembers = []) {
  const rows = Array.isArray(indices) ? indices : [];
  const messages = await Promise.all(
    rows.map(async (index) => {
      const content = await loadMergedFixedContentByIndexWithCharacterName(index, partyMembers);
      return buildMergedFixedContentPages(index, content, partyMembers);
    }),
  );
  return messages.flat();
}

export function normalizeMergedFixedContent(rawContent) {
  const normalized = String(rawContent || "")
    .trim()
    .replace(/^['"]|['"]$/g, "")
    .replace(/^>-\s*/, "")
    .replace(/\\r\\n|\\n|\\r/g, "\n")
    .replace(/\\t/g, "")
    .replace(/\[0x[0-9a-fA-F]+\]/g, "");
  return normalized
    .split("\n")
    .map((line) => line.replace(/^\t+/, "").trimEnd())
    .filter((line) => line.trim().length > 0)
    .join("\n");
}

function normalizeMapSaveShape(mapState, mapDefinition) {
  return {
    map: String(mapState?.current_map_id || mapDefinition.id || DEFAULT_MAP_ID),
    surface: String(mapDefinition?.name || mapState?.surface || mapState?.current_map_id || DEFAULT_MAP_ID),
    x: asNumber(mapState?.tile_x, mapDefinition?.spawn?.x ?? 0),
    y: asNumber(mapState?.tile_y, mapDefinition?.spawn?.y ?? 0),
  };
}

function isFloatingContinentAirshipEnabled(mapDefinition, saveEnvelope) {
  return (
    String(mapDefinition?.id || "") === FLOATING_CONTINENT_MAP_ID
    && isSavedEventFlagEnabled(saveEnvelope, AIRSHIP_OBTAINED_EVENT_FLAG)
    && !isSavedEventFlagEnabled(saveEnvelope, AIRSHIP_DESTROYED_EVENT_FLAG)
  );
}

function isFloatingContinentCanoeEnabled(mapDefinition, saveEnvelope) {
  return (
    String(mapDefinition?.id || "") === FLOATING_CONTINENT_MAP_ID
    && (
      isSavedEventFlagEnabled(saveEnvelope, CANOE_OBTAINED_EVENT_FLAG)
      || isSavedEventFlagEnabled(saveEnvelope, CASTLE_SASUNE_MAINKEEP_4F_KING_545_SPOKEN_FLAG)
    )
  );
}

function isCanoeWaterGid(gid) {
  return CANOE_WATER_GIDS.has(Number(gid || 0));
}

function resolveAirshipState(mapDefinition, mapState = {}, menuState = {}, saveEnvelope = null) {
  const available = isFloatingContinentAirshipEnabled(mapDefinition, saveEnvelope);
  if (!available) {
    return {};
  }
  const storedAirshipState = menuState?.airship_state && typeof menuState.airship_state === "object"
    ? menuState.airship_state
    : {};
  const defaultX = AIRSHIP_FLOATING_CONTINENT_TILE.x;
  const defaultY = AIRSHIP_FLOATING_CONTINENT_TILE.y;
  const airshipTileX = optionalNumber(
    mapState?.airship_tile_x,
    optionalNumber(storedAirshipState.tile_x, defaultX),
  );
  const airshipTileY = optionalNumber(
    mapState?.airship_tile_y,
    optionalNumber(storedAirshipState.tile_y, defaultY),
  );
  const riding = available && Boolean(
    mapState?.airship_riding ?? storedAirshipState.riding ?? false
  );
  return {
    airship_riding: riding,
    airship_tile_x: airshipTileX,
    airship_tile_y: airshipTileY,
  };
}

function applyResolvedAirshipState(mapDefinition, mapState = {}, menuState = {}, saveEnvelope = null) {
  return {
    ...mapState,
    ...resolveAirshipState(mapDefinition, mapState, menuState, saveEnvelope),
  };
}

export function deriveInitialMapState(appState, mapDefinition, options = {}) {
  const menuState = appState?.menuState && typeof appState.menuState === "object"
    ? appState.menuState
    : {};
  const saveEnvelope = appState?.saveEnvelope && typeof appState.saveEnvelope === "object"
    ? appState.saveEnvelope
    : {};
  const envelopeMap = appState?.saveEnvelope?.save?.map && typeof appState.saveEnvelope.save.map === "object"
    ? appState.saveEnvelope.save.map
    : {};
  const menuMapState = menuState?.map_state && typeof menuState.map_state === "object"
    ? menuState.map_state
    : {};
  const wantedMapId = String(
    menuMapState.current_map_id
    || envelopeMap.map
    || mapDefinition?.id
    || DEFAULT_MAP_ID,
  );
  const savedOpenedTreasures = readSavedTreasureStates(saveEnvelope, wantedMapId);
  const shouldResumeFromSavedPosition = Boolean(options?.resumeFromSavedPosition);
  if (shouldResumeFromSavedPosition) {
    const airshipState = resolveAirshipState(mapDefinition, menuMapState, menuState, saveEnvelope);
    return {
      current_map_id: wantedMapId,
      tile_x: asNumber(menuMapState.tile_x, asNumber(envelopeMap.x, asNumber(mapDefinition?.spawn?.x, 0))),
      tile_y: asNumber(menuMapState.tile_y, asNumber(envelopeMap.y, asNumber(mapDefinition?.spawn?.y, 0))),
      current_movement_plane: normalizeMovementPlane(menuMapState.current_movement_plane, "ground"),
      facing_direction: normalizeMapFacingDirection(menuMapState.facing_direction, "down"),
      steps_since_reset: asNumber(menuMapState.steps_since_reset, 0),
      switch_states: normalizeSwitchStates(menuMapState.switch_states),
      opened_treasures: mergeTreasureStates(savedOpenedTreasures, menuMapState.opened_treasures),
      ...airshipState,
    };
  }
  const floatingSelection = resolveFloatingContinentSelection(mapDefinition, {
    selected_location_group: appState?.selectedLocationGroup,
    selected_location: appState?.selectedLocation,
  });
  const initialSpawn = isFloatingContinentMap(mapDefinition)
    ? resolveFloatingContinentSpawn(floatingSelection.selected_location, mapDefinition?.spawn)
    : {
      x: asNumber(mapDefinition?.spawn?.x, 0),
      y: asNumber(mapDefinition?.spawn?.y, 0),
    };
  const airshipState = isFloatingContinentMap(mapDefinition)
    ? resolveFloatingContinentFreshAirshipState(
      floatingSelection.selected_location,
      saveEnvelope,
    )
    : resolveAirshipState(mapDefinition, {}, menuState, saveEnvelope);
  return {
    current_map_id: String(mapDefinition?.id || wantedMapId || DEFAULT_MAP_ID),
    tile_x: asNumber(initialSpawn.x, 0),
    tile_y: asNumber(initialSpawn.y, 0),
    current_movement_plane: "ground",
    steps_since_reset: 0,
    switch_states: {},
    opened_treasures: savedOpenedTreasures,
    ...airshipState,
  };
}

export function canOccupyTile(mapDefinition, x, y, saveEnvelope = null) {
  if (!mapDefinition) return false;
  if (x < 0 || y < 0 || x >= mapDefinition.width || y >= mapDefinition.height) {
    return false;
  }
  if (findBlockingObjectAt(mapDefinition, x, y, saveEnvelope)) {
    return false;
  }
  const gid = Number(mapDefinition.rows?.[y]?.[x] ?? 0);
  if (!mapDefinition.collisionGids.has(gid)) {
    return true;
  }
  return Boolean(
    isFloatingContinentCanoeEnabled(mapDefinition, saveEnvelope)
    && isCanoeWaterGid(gid)
  );
}

function resolveMovementLayer(mapDefinition, x, y) {
  if (!mapDefinition || x < 0 || y < 0 || x >= mapDefinition.width || y >= mapDefinition.height) {
    return null;
  }
  if (!Array.isArray(mapDefinition.movementRows)) {
    return null;
  }
  return asNumber(mapDefinition.movementRows?.[y]?.[x], 0);
}

function findMovementPlaneTile(mapDefinition, x, y) {
  const tiles = Array.isArray(mapDefinition?.movementPlaneTiles) ? mapDefinition.movementPlaneTiles : [];
  return tiles.find((row) => Number(row?.x) === Number(x) && Number(row?.y) === Number(y)) || null;
}

function resolveMovementLayerCandidates(mapDefinition, x, y) {
  const baseLayer = resolveMovementLayer(mapDefinition, x, y);
  if (baseLayer === null) {
    return [];
  }
  const planeTile = findMovementPlaneTile(mapDefinition, x, y);
  if (!planeTile) {
    return [{ plane: "ground", layer: baseLayer }];
  }
  const planeEntries = Object.entries(planeTile.planes || {})
    .map(([plane, layer]) => ({
      plane: normalizeMovementPlane(plane, planeTile.defaultPlane || "ground"),
      layer: asNumber(layer, 0),
    }))
    .filter((row) => row.layer > 0);
  if (planeEntries.length) {
    return planeEntries;
  }
  return [{ plane: normalizeMovementPlane(planeTile.defaultPlane, "ground"), layer: baseLayer }];
}

function resolveEffectiveMovementLayer(mapDefinition, x, y, currentPlane = "ground") {
  const candidates = resolveMovementLayerCandidates(mapDefinition, x, y);
  if (!candidates.length) return null;
  return candidates.find((row) => row.plane === normalizeMovementPlane(currentPlane, "ground"))?.layer
    ?? candidates[0].layer;
}

function hasDirectedMovementEdge(mapDefinition, fromX, fromY, toX, toY) {
  const edges = Array.isArray(mapDefinition?.movementEdges) ? mapDefinition.movementEdges : [];
  return edges.some((edge) => (
    (
      Number(edge?.from?.x) === Number(fromX)
      && Number(edge?.from?.y) === Number(fromY)
      && Number(edge?.to?.x) === Number(toX)
      && Number(edge?.to?.y) === Number(toY)
    )
    || (
      edge?.bidirectional !== false
      && Number(edge?.from?.x) === Number(toX)
      && Number(edge?.from?.y) === Number(toY)
      && Number(edge?.to?.x) === Number(fromX)
      && Number(edge?.to?.y) === Number(fromY)
    )
  ));
}

function canTraverseBetweenTiles(mapDefinition, fromX, fromY, toX, toY, saveEnvelope = null, currentPlane = "ground") {
  if (!canOccupyTile(mapDefinition, toX, toY, saveEnvelope)) {
    return false;
  }
  const fromLayer = resolveEffectiveMovementLayer(mapDefinition, fromX, fromY, currentPlane);
  const toCandidates = resolveMovementLayerCandidates(mapDefinition, toX, toY);
  if (fromLayer === null || !toCandidates.length) {
    return true;
  }
  if (toCandidates.some((candidate) => candidate.layer === fromLayer)) {
    return true;
  }
  return hasDirectedMovementEdge(mapDefinition, fromX, fromY, toX, toY);
}

function resolveTraversalTargetPlane(mapDefinition, fromX, fromY, toX, toY, currentPlane = "ground") {
  const normalizedCurrentPlane = normalizeMovementPlane(currentPlane, "ground");
  const fromLayer = resolveEffectiveMovementLayer(mapDefinition, fromX, fromY, normalizedCurrentPlane);
  const toCandidates = resolveMovementLayerCandidates(mapDefinition, toX, toY);
  if (!toCandidates.length) {
    return normalizedCurrentPlane;
  }
  const sameLayerCandidate = toCandidates.find((candidate) => candidate.layer === fromLayer);
  if (sameLayerCandidate) {
    return sameLayerCandidate.plane;
  }
  const samePlaneCandidate = toCandidates.find((candidate) => candidate.plane === normalizedCurrentPlane);
  if (samePlaneCandidate) {
    return samePlaneCandidate.plane;
  }
  return toCandidates[0].plane;
}

function isWithinMapBounds(mapDefinition, x, y) {
  return Boolean(
    mapDefinition
    && x >= 0
    && y >= 0
    && x < mapDefinition.width
    && y < mapDefinition.height,
  );
}

export function resolveTransitionSpawn(mapDefinition, targetSpawn = null) {
  const fallbackX = asNumber(mapDefinition?.spawn?.x, 0);
  const fallbackY = asNumber(mapDefinition?.spawn?.y, 0);
  const hasExplicitTarget = Number.isFinite(Number(targetSpawn?.x))
    && Number.isFinite(Number(targetSpawn?.y));
  const targetX = asNumber(targetSpawn?.x, fallbackX);
  const targetY = asNumber(targetSpawn?.y, fallbackY);

  // Explicit exit destinations should be authoritative as long as they stay on-map.
  // Some maps intentionally land the player on trigger tiles, and collision metadata
  // is not always reliable enough to override a hand-authored target_spawn.
  if (hasExplicitTarget && isWithinMapBounds(mapDefinition, targetX, targetY)) {
    return { x: targetX, y: targetY };
  }
  if (canOccupyTile(mapDefinition, targetX, targetY)) {
    return { x: targetX, y: targetY };
  }
  return { x: fallbackX, y: fallbackY };
}

export function findBlockingObjectAt(mapDefinition, x, y, saveEnvelope = null) {
  return (mapDefinition?.objects || []).find((row) => (
    isMapObjectAvailable(row, saveEnvelope)
    && (
      (row?.type === "npc" && row?.blocking !== false)
      || row?.blocking === true
    )
    && Number(row?.x) === Number(x)
    && Number(row?.y) === Number(y)
  )) || null;
}

function directionDelta(direction) {
  return {
    up: { x: 0, y: -1 },
    down: { x: 0, y: 1 },
    left: { x: -1, y: 0 },
    right: { x: 1, y: 0 },
  }[direction] || null;
}

function buildAxisAlignedPath(startPosition, endPosition, options = {}) {
  const startX = Number(startPosition?.x);
  const startY = Number(startPosition?.y);
  const endX = Number(endPosition?.x);
  const endY = Number(endPosition?.y);
  if (![startX, startY, endX, endY].every((value) => Number.isFinite(value))) {
    return [];
  }
  const horizontalFirst = options?.horizontalFirst !== false;
  const points = [];
  let currentX = startX;
  let currentY = startY;
  const pushHorizontal = () => {
    while (currentX !== endX) {
      currentX += currentX < endX ? 1 : -1;
      points.push({ x: currentX, y: currentY });
    }
  };
  const pushVertical = () => {
    while (currentY !== endY) {
      currentY += currentY < endY ? 1 : -1;
      points.push({ x: currentX, y: currentY });
    }
  };
  if (horizontalFirst) {
    pushHorizontal();
    pushVertical();
  } else {
    pushVertical();
    pushHorizontal();
  }
  return points;
}

export function canNpcOccupyTile(mapDefinition, npcRow, mapState, x, y, saveEnvelope = null) {
  if (!mapDefinition) return false;
  if (x < 0 || y < 0 || x >= mapDefinition.width || y >= mapDefinition.height) {
    return false;
  }
  if (
    Number(mapState?.tile_x) === Number(x)
    && Number(mapState?.tile_y) === Number(y)
  ) {
    return false;
  }
  const occupiedObject = (mapDefinition?.objects || []).find((row) => (
    row !== npcRow
    && isMapObjectAvailable(row, saveEnvelope)
    && row?.blocking !== false
    && Number(row?.x) === Number(x)
    && Number(row?.y) === Number(y)
  ));
  if (occupiedObject) {
    return false;
  }
  const gid = Number(mapDefinition.rows?.[y]?.[x] ?? 0);
  if (!mapDefinition.collisionGids.has(gid)) {
    return true;
  }
  return Boolean(
    isFloatingContinentCanoeEnabled(mapDefinition, saveEnvelope)
    && isCanoeWaterGid(gid)
  );
}

function canNpcTraverseBetweenTiles(mapDefinition, npcRow, mapState, fromX, fromY, toX, toY, saveEnvelope = null) {
  if (!canNpcOccupyTile(mapDefinition, npcRow, mapState, toX, toY, saveEnvelope)) {
    return false;
  }
  const fromLayer = resolveMovementLayer(mapDefinition, fromX, fromY);
  const toLayer = resolveMovementLayer(mapDefinition, toX, toY);
  if (fromLayer === null || toLayer === null) {
    return true;
  }
  if (fromLayer === toLayer) {
    return true;
  }
  return hasDirectedMovementEdge(mapDefinition, fromX, fromY, toX, toY);
}

export function canAirshipOccupyTile(mapDefinition, x, y) {
  if (!mapDefinition) return false;
  if (x < 0 || y < 0 || x >= mapDefinition.width || y >= mapDefinition.height) {
    return false;
  }
  if (findBlockingObjectAt(mapDefinition, x, y, null)) {
    return false;
  }
  const gid = Number(mapDefinition.rows?.[y]?.[x] ?? 0);
  return !AIRSHIP_BLOCKED_GIDS.has(gid);
}

export function shouldTriggerFloatingContinentBigRockCrash(
  mapDefinition,
  mapState,
  nextX,
  nextY,
  saveEnvelope = null,
) {
  return Boolean(
    isFloatingContinentMap(mapDefinition)
    && isAirshipRiding(mapDefinition, mapState, saveEnvelope)
    && Number(nextX) === FLOATING_CONTINENT_BIG_ROCK_CRASH_TILE.x
    && Number(nextY) === FLOATING_CONTINENT_BIG_ROCK_CRASH_TILE.y
    && isSavedEventFlagEnabled(saveEnvelope, SEALED_CAVE_SARA_LEAVE_EVENT_FLAG)
    && isSavedEventFlagEnabled(saveEnvelope, KAZUS_CID_FOLLOWER_EVENT_FLAG)
    && isSavedEventFlagEnabled(saveEnvelope, KAZUS_BLACKSMITH_MITHRIL_RAM_EVENT_FLAG)
    && !isSavedEventFlagEnabled(saveEnvelope, AIRSHIP_DESTROYED_EVENT_FLAG)
  );
}

export function moveMapPosition(mapDefinition, mapState, direction, saveEnvelope = null) {
  const facingDirection = normalizeMapFacingDirection(direction, mapState?.facing_direction || "down");
  const delta = directionDelta(facingDirection);
  if (!delta) {
    return {
      moved: false,
      nextState: {
        ...mapState,
        facing_direction: facingDirection,
      },
      reason: "invalid",
    };
  }
  const nextX = asNumber(mapState?.tile_x, 0) + delta.x;
  const nextY = asNumber(mapState?.tile_y, 0) + delta.y;
  if (!canTraverseBetweenTiles(
    mapDefinition,
    asNumber(mapState?.tile_x, 0),
    asNumber(mapState?.tile_y, 0),
    nextX,
    nextY,
    saveEnvelope,
    mapState?.current_movement_plane,
  )) {
    return {
      moved: false,
      nextState: {
        ...mapState,
        facing_direction: facingDirection,
      },
      reason: "blocked",
    };
  }
  return {
    moved: true,
    nextState: {
      ...mapState,
      tile_x: nextX,
      tile_y: nextY,
      current_movement_plane: resolveTraversalTargetPlane(
        mapDefinition,
        asNumber(mapState?.tile_x, 0),
        asNumber(mapState?.tile_y, 0),
        nextX,
        nextY,
        mapState?.current_movement_plane,
      ),
      facing_direction: facingDirection,
      steps_since_reset: asNumber(mapState?.steps_since_reset, 0) + 1,
    },
    reason: "moved",
  };
}

function isAirshipRiding(mapDefinition, mapState, saveEnvelope = null) {
  return Boolean(
    isFloatingContinentAirshipEnabled(mapDefinition, saveEnvelope)
    && mapState?.airship_riding === true
  );
}

function isStandingOnAirship(mapDefinition, mapState, saveEnvelope = null) {
  return Boolean(
    isFloatingContinentAirshipEnabled(mapDefinition, saveEnvelope)
    && mapState?.airship_riding !== true
    && Number(mapState?.tile_x) === Number(mapState?.airship_tile_x)
    && Number(mapState?.tile_y) === Number(mapState?.airship_tile_y)
  );
}

function canOccupyCurrentTravelMode(mapDefinition, mapState, saveEnvelope = null) {
  if (isAirshipRiding(mapDefinition, mapState, saveEnvelope)) {
    return canAirshipOccupyTile(mapDefinition, mapState?.tile_x, mapState?.tile_y);
  }
  return canOccupyTile(mapDefinition, mapState?.tile_x, mapState?.tile_y, saveEnvelope);
}

export function moveAirshipPosition(mapDefinition, mapState, direction, saveEnvelope = null) {
  const facingDirection = normalizeMapFacingDirection(direction, mapState?.facing_direction || "down");
  const delta = directionDelta(facingDirection);
  if (!delta) {
    return {
      moved: false,
      nextState: {
        ...mapState,
        facing_direction: facingDirection,
      },
      reason: "invalid",
    };
  }
  if (!isAirshipRiding(mapDefinition, mapState, saveEnvelope)) {
    return {
      moved: false,
      nextState: {
        ...mapState,
        facing_direction: facingDirection,
      },
      reason: "inactive",
    };
  }
  const nextX = asNumber(mapState?.tile_x, 0) + delta.x;
  const nextY = asNumber(mapState?.tile_y, 0) + delta.y;
  if (!canAirshipOccupyTile(mapDefinition, nextX, nextY)) {
    return {
      moved: false,
      nextState: {
        ...mapState,
        facing_direction: facingDirection,
      },
      reason: "blocked",
    };
  }
  return {
    moved: true,
    nextState: {
      ...mapState,
      tile_x: nextX,
      tile_y: nextY,
      airship_tile_x: nextX,
      airship_tile_y: nextY,
      current_movement_plane: normalizeMovementPlane(mapState?.current_movement_plane, "ground"),
      facing_direction: facingDirection,
      steps_since_reset: asNumber(mapState?.steps_since_reset, 0) + 1,
    },
    reason: "moved",
  };
}

function buildEnvelopeWithMapState(store, nextMapState, mapDefinition, options = {}) {
  const currentState = store.getState();
  const normalizedMapState = {
    ...(nextMapState && typeof nextMapState === "object" ? nextMapState : {}),
    current_movement_plane: normalizeMovementPlane(nextMapState?.current_movement_plane, "ground"),
  };
  const currentEnvelope = currentState.saveEnvelope && typeof currentState.saveEnvelope === "object"
    ? currentState.saveEnvelope
    : {
      version: 1,
      save: {},
      menu_state: {},
      selected_location_group: currentState.selectedLocationGroup,
      selected_location: currentState.selectedLocation,
      saved_at: new Date().toISOString(),
    };
  const nextMenuState = {
    ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
    map_state: {
      ...normalizedMapState,
    },
  };
  const currentAirshipState = currentState.menuState?.airship_state && typeof currentState.menuState.airship_state === "object"
    ? currentState.menuState.airship_state
    : null;
  if (Number.isFinite(Number(nextMapState?.airship_tile_x)) && Number.isFinite(Number(nextMapState?.airship_tile_y))) {
    nextMenuState.airship_state = {
      tile_x: Number(nextMapState.airship_tile_x),
      tile_y: Number(nextMapState.airship_tile_y),
      riding: Boolean(nextMapState.airship_riding),
    };
  } else if (options?.clearAirshipState === true) {
    delete nextMenuState.airship_state;
  } else if (currentAirshipState) {
    nextMenuState.airship_state = currentAirshipState;
  }
  const nextSave = {
    ...(currentEnvelope.save && typeof currentEnvelope.save === "object" ? currentEnvelope.save : {}),
    map: normalizeMapSaveShape(normalizedMapState, mapDefinition),
  };
  writeSavedTreasureStates(
    { save: nextSave },
    normalizedMapState?.current_map_id || mapDefinition?.id,
    normalizedMapState?.opened_treasures,
  );
  return {
    ...currentEnvelope,
    save: nextSave,
    menu_state: nextMenuState,
    selected_location_group: currentState.selectedLocationGroup,
    selected_location: currentState.selectedLocation,
    saved_at: new Date().toISOString(),
  };
}

function renderLayout() {
  return `
    <style>
      [data-screen="map"] {
        --map-tile-size: ${DISPLAY_TILE_SIZE}px;
      }
      [data-screen="map"] .map-frame {
        display: grid;
        gap: 12px;
      }
      [data-screen="map"] .map-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
      }
      [data-screen="map"] .map-toolbar-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      [data-screen="map"] .map-viewport {
        position: relative;
        width: min(92vw, 440px);
        aspect-ratio: 1 / 1;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.22);
        border-radius: 14px;
        background:
          radial-gradient(circle at top, rgba(255, 255, 255, 0.08), transparent 40%),
          linear-gradient(180deg, rgba(7, 13, 30, 0.94), rgba(8, 14, 34, 0.98));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        margin: 0 auto;
      }
      [data-screen="map"] .map-layer {
        position: absolute;
        left: 0;
        top: 0;
        transform-origin: top left;
        will-change: transform;
      }
      [data-screen="map"] .map-tile {
        position: absolute;
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        background-repeat: no-repeat;
        image-rendering: pixelated;
        overflow: hidden;
      }
      [data-screen="map"] .map-water-highlight {
        position: absolute;
        inset: 0;
        background-image: var(--water-highlight-url);
        background-repeat: no-repeat;
        background-size: var(--map-tile-size) var(--map-tile-size);
        image-rendering: pixelated;
        opacity: 0.82;
        pointer-events: none;
        animation: map-water-highlight 1800ms steps(${WATER_HIGHLIGHT_SHIFT_PX}) infinite;
        will-change: transform;
      }
      [data-screen="map"] .map-water-flow-canvas {
        position: absolute;
        top: 0;
        image-rendering: pixelated;
        opacity: 1;
        pointer-events: none;
        animation: map-water-flow ${WATER_FLOW_ANIMATION_MS}ms steps(${WATER_FLOW_SHIFT_PX}) infinite;
        will-change: transform;
      }
      [data-screen="map"] .map-object {
        position: absolute;
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        display: grid;
        place-items: center;
        font-size: 0.6rem;
        font-weight: 700;
        color: #f7f2cc;
        text-shadow: 0 1px 0 rgba(0, 0, 0, 0.8);
        pointer-events: none;
      }
      [data-screen="map"] .map-object-npc {
        width: ${NPC_DISPLAY_TILE_SIZE}px;
        height: ${NPC_DISPLAY_TILE_SIZE}px;
        contain: paint;
        transition: transform ${MAP_MOVE_ANIMATION_MS}ms linear;
        will-change: transform;
      }
      [data-screen="map"] .map-object-image::before {
        display: none;
      }
      [data-screen="map"] .map-object::before {
        content: "";
        position: absolute;
        inset: 3px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.55);
        background: rgba(0, 0, 0, 0.28);
      }
      [data-screen="map"] .map-object > span {
        position: relative;
        z-index: 1;
      }
      [data-screen="map"] .map-object-npc::before {
        display: none;
      }
      [data-screen="map"] .map-object-sprite {
        display: block;
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        background-image: var(--object-sprite-url);
        background-repeat: no-repeat;
        background-size:
          calc(var(--map-tile-size) * var(--object-frame-count, 1))
          var(--map-tile-size);
        background-position: 0 0;
        image-rendering: pixelated;
        filter: drop-shadow(0 2px 0 rgba(0, 0, 0, 0.35));
      }
      [data-screen="map"] .map-object-sprite.is-animated {
        animation-name: map-object-frames;
        animation-timing-function: steps(var(--object-frame-count, 1));
        animation-iteration-count: infinite;
      }
      [data-screen="map"] .map-npc-sprite {
        display: block;
        width: ${NPC_DISPLAY_TILE_SIZE}px;
        height: ${NPC_DISPLAY_TILE_SIZE}px;
        background-image: var(--npc-sprite-url);
        background-repeat: no-repeat;
        background-size: ${NPC_DISPLAY_TILE_SIZE * NPC_SHEET_COLUMNS}px ${NPC_DISPLAY_TILE_SIZE}px;
        background-position: 0 0;
        image-rendering: pixelated;
        filter: drop-shadow(0 2px 0 rgba(0, 0, 0, 0.45));
      }
      [data-screen="map"] .map-follower {
        position: absolute;
        left: 0;
        top: 0;
        width: ${NPC_DISPLAY_TILE_SIZE}px;
        height: ${NPC_DISPLAY_TILE_SIZE}px;
        contain: paint;
        pointer-events: none;
        will-change: transform;
        z-index: 1;
      }
      [data-screen="map"] .map-decoration {
        position: absolute;
        pointer-events: none;
        image-rendering: pixelated;
      }
      [data-screen="map"] .map-decoration-ring {
        width: 4px;
        height: 4px;
        border-radius: 999px;
        background: radial-gradient(circle at 35% 35%, #fff8d6 0%, #f1e38a 50%, #8b6f1d 100%);
        box-shadow:
          0 0 0 1px rgba(72, 47, 10, 0.7),
          0 0 6px rgba(255, 232, 126, 0.45);
        z-index: 3;
      }
      [data-screen="map"] .map-airship {
        position: absolute;
        pointer-events: none;
        image-rendering: pixelated;
        background-image: url("${AIRSHIP_IMAGE_URL}");
        background-repeat: no-repeat;
        background-size: calc(var(--map-tile-size) * ${AIRSHIP_SPRITE_FRAMES}) var(--map-tile-size);
        filter: drop-shadow(0 2px 0 rgba(0, 0, 0, 0.45));
        z-index: 2;
      }
      [data-screen="map"] .map-airship-ground,
      [data-screen="map"] .map-airship-lower,
      [data-screen="map"] .map-airship-upper {
        width: var(--map-tile-size);
        height: var(--map-tile-size);
      }
      [data-screen="map"] .map-airship-ground {
        background-position: 0 0;
      }
      [data-screen="map"] .map-airship-lower {
        background-position: calc(var(--map-tile-size) * -1) 0;
      }
      [data-screen="map"] .map-airship-upper {
        background-position: calc(var(--map-tile-size) * var(--airship-upper-start-frame, -2)) 0;
        animation: map-airship-upper 1000ms steps(2) infinite;
        transform: scaleX(var(--airship-facing-scale, 1));
        transform-origin: center;
      }
      [data-screen="map"] .map-airship-crash-piece,
      [data-screen="map"] .map-airship-crash-burst {
        position: absolute;
        pointer-events: none;
        will-change: transform, opacity;
        z-index: 4;
      }
      [data-screen="map"] .map-airship-crash-piece {
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        background-image: url("${AIRSHIP_IMAGE_URL}");
        background-repeat: no-repeat;
        background-size: calc(var(--map-tile-size) * ${AIRSHIP_SPRITE_FRAMES}) var(--map-tile-size);
        background-position: 0 0;
        image-rendering: pixelated;
        transform-origin: center;
        filter: drop-shadow(0 1px 0 rgba(0, 0, 0, 0.4));
      }
      [data-screen="map"] .map-airship-crash-burst {
        width: calc(var(--map-tile-size) * 0.9);
        height: calc(var(--map-tile-size) * 0.9);
        border-radius: 999px;
        background: radial-gradient(circle, rgba(255,245,190,0.98) 0%, rgba(255,182,76,0.95) 45%, rgba(255,112,32,0.75) 65%, rgba(255,112,32,0) 100%);
        mix-blend-mode: screen;
      }
      [data-screen="map"] .map-decoration-crystal {
        width: var(--map-tile-size);
        height: calc(var(--map-tile-size) * 2);
        background-image: url("${CRYSTAL_IMAGE_URL}");
        background-repeat: no-repeat;
        background-size: calc(var(--map-tile-size) * ${CRYSTAL_SPRITE_FRAMES}) calc(var(--map-tile-size) * 2);
        animation: map-crystal-frames ${CRYSTAL_SPRITE_FRAMES * CRYSTAL_SPRITE_FRAME_MS}ms steps(${CRYSTAL_SPRITE_FRAMES}) infinite;
        z-index: 1;
      }
      [data-screen="map"] .map-player {
        position: absolute;
        left: var(--player-left, 50%);
        top: var(--player-top, 50%);
        width: ${CHARACTER_DISPLAY_TILE_SIZE}px;
        height: ${CHARACTER_DISPLAY_TILE_SIZE}px;
        transform: translate(-50%, -50%) scaleX(var(--player-facing-scale, 1));
        transform-origin: center;
        background-image: var(--player-sprite-url, url("${ONION_KNIGHT_IMAGE_URL}"));
        background-repeat: no-repeat;
        background-size:
          calc(${CHARACTER_DISPLAY_TILE_SIZE}px * var(--player-sprite-columns, ${CHARACTER_SHEET_COLUMNS}))
          calc(${CHARACTER_DISPLAY_TILE_SIZE}px * var(--player-sprite-rows, 4));
        image-rendering: pixelated;
        filter: drop-shadow(0 2px 0 rgba(0, 0, 0, 0.45));
        z-index: 2;
      }
      [data-screen="map"] .map-hud {
        display: grid;
        gap: 10px;
      }
      [data-screen="map"] .map-flash {
        position: absolute;
        inset: 0;
        pointer-events: none;
        opacity: 0;
        background: rgba(255, 255, 255, 0.92);
        z-index: 3;
      }
      [data-screen="map"] .map-flash.active {
        animation: map-screen-flash 380ms ease-out;
      }
      [data-screen="map"] .map-event-overlay {
        position: absolute;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        padding: 18px;
        background: rgba(7, 13, 30, 0.72);
        z-index: 4;
      }
      [data-screen="map"] .map-event-overlay.open {
        display: flex;
      }
      [data-screen="map"] .map-event-card {
        width: min(100%, 340px);
        padding: 14px 16px;
        border: 2px solid rgba(255, 255, 255, 0.72);
        border-radius: 12px;
        background: rgba(8, 14, 34, 0.96);
        color: #f4f7ff;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.34);
      }
      [data-screen="map"] .map-event-text {
        margin: 0;
        white-space: pre-wrap;
        line-height: 1.65;
      }
      [data-screen="map"] .map-event-actions {
        display: flex;
        justify-content: center;
        margin-top: 14px;
      }
      @keyframes map-screen-flash {
        0% { opacity: 0; }
        18% { opacity: 0.95; }
        100% { opacity: 0; }
      }
      @keyframes map-crystal-frames {
        from { background-position: 0 0; }
        to { background-position: calc(var(--map-tile-size) * -${CRYSTAL_SPRITE_FRAMES}) 0; }
      }
      @keyframes map-object-frames {
        from { background-position: 0 0; }
        to { background-position: calc(var(--map-tile-size) * var(--object-frame-count, 1) * -1) 0; }
      }
      @keyframes map-airship-upper {
        from { background-position: calc(var(--map-tile-size) * var(--airship-upper-start-frame, -2)) 0; }
        to { background-position: calc(var(--map-tile-size) * var(--airship-upper-end-frame, -3)) 0; }
      }
      @keyframes map-water-highlight {
        from { transform: translateX(0); }
        to { transform: translateX(${WATER_HIGHLIGHT_SHIFT_PX}px); }
      }
      @keyframes map-water-flow {
        from { transform: translateX(0); }
        to { transform: translateX(${WATER_FLOW_SHIFT_PX}px); }
      }
      [data-screen="map"] .map-meta {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        color: rgba(255, 255, 255, 0.84);
      }
      [data-screen="map"] .map-pad {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 18px;
        flex-wrap: wrap;
      }
      [data-screen="map"] .map-pad-dpad {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 68px));
        gap: 8px;
      }
      [data-screen="map"] .map-pad-actions {
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
        align-items: center;
      }
      [data-screen="map"] .map-pad-spacer {
        visibility: hidden;
      }
      [data-screen="map"] .map-pad-btn {
        min-height: 54px;
        font-size: 1rem;
        font-weight: 700;
        touch-action: manipulation;
        user-select: none;
        -webkit-user-select: none;
      }
      [data-screen="map"] .map-pad-action {
        min-width: 88px;
        min-height: 54px;
        border-radius: 999px;
        letter-spacing: 0.08em;
      }
      @media (max-width: 480px) {
        [data-screen="map"] .map-toolbar,
        [data-screen="map"] .map-meta {
          flex-direction: column;
          align-items: stretch;
        }
        [data-screen="map"] .map-toolbar-actions {
          justify-content: stretch;
        }
        [data-screen="map"] .map-toolbar-actions .btn {
          flex: 1 1 auto;
        }
      }
    </style>
    <div class="screen medium" data-screen="map">
      <section class="frame map-frame">
        <div class="map-toolbar">
          <div>
            <h1 class="title" style="margin:0;">MAP</h1>
            <div id="mapStatus" class="status" style="margin-top:6px;">マップを読み込み中...</div>
          </div>
          <div class="map-toolbar-actions">
            <button id="locationBtn" class="btn" type="button">Location</button>
            <button id="menuBtn" class="btn" type="button">メニュー</button>
            <button id="battleBtn" class="btn" type="button">戦闘</button>
          </div>
        </div>

        <div id="mapViewport" class="map-viewport" aria-label="map viewport">
          <div id="mapLayer" class="map-layer"></div>
          <div class="map-player" aria-hidden="true"></div>
          <div id="mapFlash" class="map-flash" aria-hidden="true"></div>
          <div id="mapEventOverlay" class="map-event-overlay" aria-hidden="true">
            <div class="map-event-card">
              <p id="mapEventText" class="map-event-text"></p>
              <div class="map-event-actions">
                <button id="mapEventCloseBtn" class="btn" type="button">閉じる</button>
              </div>
            </div>
          </div>
        </div>

        <div class="map-hud">
          <div id="mapMeta" class="map-meta"></div>
          <div class="map-pad">
            <div class="map-pad-dpad">
              <span class="map-pad-spacer"></span>
              <button class="btn map-pad-btn" type="button" data-dir="up">↑</button>
              <span class="map-pad-spacer"></span>
              <button class="btn map-pad-btn" type="button" data-dir="left">←</button>
              <button class="btn map-pad-btn" type="button" data-dir="down">↓</button>
              <button class="btn map-pad-btn" type="button" data-dir="right">→</button>
            </div>
            <div class="map-pad-actions">
              <button id="confirmBtn" class="btn map-pad-btn map-pad-action" type="button">A</button>
              <button id="cancelBtn" class="btn map-pad-btn map-pad-action" type="button">B</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  `;
}

function objectLabel(type) {
  if (type === "exit") return "EXIT";
  if (type === "switch") return "SW";
  if (type === "chest" || type === "treasure") return "宝";
  if (type === "npc") return "";
  return "OBJ";
}

const NPC_RUNTIME_KEY = Symbol("npcRuntimeKey");

export function npcObjectKey(row, fallback = "") {
  if (!row || typeof row !== "object") return String(fallback);
  if (row[NPC_RUNTIME_KEY]) return row[NPC_RUNTIME_KEY];
  if (row?.npc_key) {
    row[NPC_RUNTIME_KEY] = String(row.npc_key);
    return row[NPC_RUNTIME_KEY];
  }
  const parts = [];
  if (row?.name) parts.push(`name:${row.name}`);
  if (row?.dialogue_index !== undefined && row?.dialogue_index !== null && row?.dialogue_index !== "") {
    parts.push(`dialogue:${row.dialogue_index}`);
  }
  if (Number.isFinite(Number(row?.x)) && Number.isFinite(Number(row?.y))) {
    parts.push(`spawn:${Number(row.x)},${Number(row.y)}`);
  }
  const spriteSource = row?.sprite_image || row?.spriteImageUrl;
  if (spriteSource) parts.push(`sprite:${spriteSource}`);
  if (fallback !== "") parts.push(`fallback:${String(fallback)}`);
  row[NPC_RUNTIME_KEY] = parts.length > 0 ? parts.join("|") : String(fallback);
  return row[NPC_RUNTIME_KEY];
}

function resolveObjectSpriteFrameCount(row) {
  const value = Number(row?.sprite_frames ?? row?.frame_count ?? 1);
  return Number.isFinite(value) && value > 0 ? Math.max(1, Math.floor(value)) : 1;
}

function resolveObjectSpriteFrameMs(row) {
  const value = Number(row?.sprite_frame_ms ?? row?.frame_ms ?? 1000);
  return Number.isFinite(value) && value > 0 ? Math.max(1, Math.floor(value)) : 1000;
}

function npcTileTransform(row, renderPadding = { left: 0, top: 0 }, tileSize = DISPLAY_TILE_SIZE) {
  const x = (Number(row?.x || 0) + Number(renderPadding?.left || 0)) * tileSize;
  const y = (Number(row?.y || 0) + Number(renderPadding?.top || 0)) * tileSize;
  return `translate3d(${x}px, ${y}px, 0)`;
}

function mapRenderSignature(mapDefinition, saveEnvelope = null) {
  return [
    String(mapDefinition?.id || ""),
    Number(mapDefinition?.renderWidth || 0),
    Number(mapDefinition?.renderHeight || 0),
    String(mapDefinition?.tileset?.imageUrl || ""),
    Number(mapDefinition?.tileset?.columns || 0),
    Number(mapDefinition?.tileset?.tileCount || 0),
    JSON.stringify(mapDefinition?.renderPadding || {}),
    JSON.stringify(
      renderableMapObjects(mapDefinition, saveEnvelope).map((row) => ({
          type: String(row?.type || ""),
          name: String(row?.name || ""),
          x: Number(row?.x || 0),
          y: Number(row?.y || 0),
          spriteImageUrl: String(row?.spriteImageUrl || ""),
          spriteFrames: Number(row?.sprite_frames ?? row?.frame_count ?? 1),
          spriteAnimate: row?.sprite_animate !== false,
        })),
    ),
    JSON.stringify(findCrystalSpriteOrigin(mapDefinition)),
  ].join("|");
}

function getWaterAnimationGidsForMap(mapDefinition) {
  const tilesetName = String(mapDefinition?.tileset?.name || "");
  return WATER_ANIMATION_GIDS_BY_TILESET_NAME[tilesetName] || WATER_ANIMATION_GIDS;
}

function getWaterFlowTileGidsForMap(mapDefinition) {
  const tilesetName = String(mapDefinition?.tileset?.name || "");
  return WATER_FLOW_TILE_GIDS_BY_TILESET_NAME[tilesetName] || WATER_FLOW_TILE_GIDS;
}

export function isWaterAnimationGid(gid, mapDefinition = null) {
  return getWaterAnimationGidsForMap(mapDefinition).has(Number(gid || 0));
}

function isWaterFlowTileGid(gid, mapDefinition = null) {
  return getWaterFlowTileGidsForMap(mapDefinition).has(Number(gid || 0));
}

function loadImageElement(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`image load failed: ${url}`));
    image.src = url;
  });
}

function createWaterFlowTile(image, gid, tilesetColumns, tilesetRows) {
  const displaySize = DISPLAY_TILE_SIZE;
  const sourceTileWidth = Math.max(1, Math.floor(image.naturalWidth / tilesetColumns));
  const sourceTileHeight = Math.max(1, Math.floor(image.naturalHeight / tilesetRows));
  const localId = Math.max(0, Number(gid || 0) - 1);
  const sourceX = (localId % tilesetColumns) * sourceTileWidth;
  const sourceY = Math.floor(localId / tilesetColumns) * sourceTileHeight;
  const canvas = document.createElement("canvas");
  canvas.width = displaySize;
  canvas.height = displaySize;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return "";
  context.imageSmoothingEnabled = false;
  context.drawImage(
    image,
    sourceX,
    sourceY,
    sourceTileWidth,
    sourceTileHeight,
    0,
    0,
    displaySize,
    displaySize,
  );
  return canvas;
}

function createWaterHighlightMask(image, gid, tilesetColumns, tilesetRows) {
  const canvas = createWaterFlowTile(image, gid, tilesetColumns, tilesetRows);
  const displaySize = DISPLAY_TILE_SIZE;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return "";

  const imageData = context.getImageData(0, 0, displaySize, displaySize);
  const pixels = imageData.data;
  let luminanceTotal = 0;
  let pixelCount = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index + 3] <= 0) continue;
    luminanceTotal += (pixels[index] * 0.299) + (pixels[index + 1] * 0.587) + (pixels[index + 2] * 0.114);
    pixelCount += 1;
  }
  const averageLuminance = pixelCount ? luminanceTotal / pixelCount : 255;
  const threshold = Math.max(108, averageLuminance + 22);
  for (let index = 0; index < pixels.length; index += 4) {
    const luminance = (pixels[index] * 0.299) + (pixels[index + 1] * 0.587) + (pixels[index + 2] * 0.114);
    if (pixels[index + 3] <= 0 || luminance < threshold) {
      pixels[index + 3] = 0;
      continue;
    }
    pixels[index + 3] = Math.min(210, pixels[index + 3]);
  }
  context.putImageData(imageData, 0, 0);
  return canvas.toDataURL("image/png");
}

function ensureWaterFlowTiles(mapDefinition) {
  const imageUrl = String(mapDefinition?.tileset?.imageUrl || "");
  if (!imageUrl) return Promise.resolve(new Map());
  const waterFlowGids = Array.from(getWaterFlowTileGidsForMap(mapDefinition));
  if (!waterFlowGids.length) return Promise.resolve(new Map());
  const tilesetColumns = Math.max(1, Number(mapDefinition?.tileset?.columns || 1));
  const tileCount = Math.max(1, Number(mapDefinition?.tileset?.tileCount || 1));
  const tilesetRows = Math.max(1, Math.ceil(tileCount / tilesetColumns));
  const cacheKey = [
    imageUrl,
    tilesetColumns,
    tilesetRows,
    waterFlowGids.join(","),
  ].join("|");
  if (!waterFlowTileCache.has(cacheKey)) {
    const request = loadImageElement(imageUrl)
      .then((image) => {
        const tiles = new Map();
        waterFlowGids.forEach((gid) => {
          tiles.set(gid, createWaterFlowTile(image, gid, tilesetColumns, tilesetRows));
        });
        return tiles;
      })
      .catch(() => new Map());
    waterFlowTileCache.set(cacheKey, request);
  }
  return waterFlowTileCache.get(cacheKey);
}

function ensureWaterHighlightMasks(mapDefinition) {
  const imageUrl = String(mapDefinition?.tileset?.imageUrl || "");
  if (!imageUrl) return Promise.resolve(new Map());
  const tilesetColumns = Math.max(1, Number(mapDefinition?.tileset?.columns || 1));
  const tileCount = Math.max(1, Number(mapDefinition?.tileset?.tileCount || 1));
  const tilesetRows = Math.max(1, Math.ceil(tileCount / tilesetColumns));
  const waterAnimationGids = getWaterAnimationGidsForMap(mapDefinition);
  const waterFlowGids = getWaterFlowTileGidsForMap(mapDefinition);
  const highlightGids = Array.from(waterAnimationGids).filter((gid) => !waterFlowGids.has(gid));
  const cacheKey = [
    imageUrl,
    tilesetColumns,
    tilesetRows,
    highlightGids.join(","),
  ].join("|");
  if (!waterHighlightMaskCache.has(cacheKey)) {
    const request = loadImageElement(imageUrl)
      .then((image) => {
        const masks = new Map();
        highlightGids.forEach((gid) => {
          masks.set(gid, createWaterHighlightMask(image, gid, tilesetColumns, tilesetRows));
        });
        return masks;
      })
      .catch(() => new Map());
    waterHighlightMaskCache.set(cacheKey, request);
  }
  return waterHighlightMaskCache.get(cacheKey);
}

function drawWaterFlowCanvas(waterCanvas, mapDefinition, masks) {
  if (!waterCanvas) return;
  const tileSize = DISPLAY_TILE_SIZE;
  const renderRows = Array.isArray(mapDefinition?.renderRows) ? mapDefinition.renderRows : [];
  const width = Math.max(1, Number(mapDefinition?.renderWidth || 0) * tileSize + WATER_FLOW_SHIFT_PX);
  const height = Math.max(1, Number(mapDefinition?.renderHeight || 0) * tileSize);
  if (waterCanvas.width !== width) waterCanvas.width = width;
  if (waterCanvas.height !== height) waterCanvas.height = height;
  waterCanvas.style.width = `${width}px`;
  waterCanvas.style.height = `${height}px`;
  waterCanvas.style.left = `${-WATER_FLOW_SHIFT_PX}px`;

  const context = waterCanvas.getContext("2d");
  if (!context) return;
  context.imageSmoothingEnabled = false;
  context.clearRect(0, 0, width, height);
  renderRows.forEach((row, y) => {
    row.forEach((gid, x) => {
      if (!isWaterFlowTileGid(gid, mapDefinition)) return;
      const rightNeighborGid = Number(renderRows[y]?.[x + 1] ?? 0);
      if (rightNeighborGid !== Number(gid || 0)) return;
      const mask = masks.get(Number(gid || 0));
      if (!mask) return;
      context.drawImage(
        mask,
        x * tileSize + WATER_FLOW_SHIFT_PX,
        y * tileSize,
      );
    });
  });
}

function applyWaterHighlightMasks(mapLayer, masks) {
  mapLayer.querySelectorAll(".map-water-highlight").forEach((node) => {
    const maskUrl = masks.get(Number(node.dataset.waterGid || 0)) || "";
    if (maskUrl) node.style.setProperty("--water-highlight-url", `url("${maskUrl}")`);
  });
}

function scheduleWaterHighlightMasks(mapLayer, mapDefinition, signature) {
  ensureWaterFlowTiles(mapDefinition).then((masks) => {
    const currentState = mapRenderStateCache.get(mapLayer);
    if (!currentState || currentState.signature !== signature) return;
    drawWaterFlowCanvas(currentState.waterCanvas, mapDefinition, masks);
  });
  ensureWaterHighlightMasks(mapDefinition).then((masks) => {
    const currentState = mapRenderStateCache.get(mapLayer);
    if (!currentState || currentState.signature !== signature) return;
    applyWaterHighlightMasks(mapLayer, masks);
  });
}

function ensureMapRenderState(mapLayer, mapDefinition, saveEnvelope = null) {
  const tileSize = DISPLAY_TILE_SIZE;
  const tilesetColumns = Number(mapDefinition?.tileset?.columns || 1);
  const tilesetRows = Math.max(1, Math.ceil(Number(mapDefinition?.tileset?.tileCount || 0) / tilesetColumns));
  const signature = mapRenderSignature(mapDefinition, saveEnvelope);
  const existing = mapRenderStateCache.get(mapLayer);
  if (existing?.signature === signature) {
    return existing;
  }

  mapLayer.innerHTML = "";
  mapLayer.style.width = `${mapDefinition.renderWidth * tileSize}px`;
  mapLayer.style.height = `${mapDefinition.renderHeight * tileSize}px`;

  const tileNodes = [];
  mapDefinition.renderRows.forEach((row, y) => {
    row.forEach((_gid, x) => {
      const tile = document.createElement("div");
      tile.className = "map-tile";
      tile.style.left = `${x * tileSize}px`;
      tile.style.top = `${y * tileSize}px`;
      tile.style.backgroundImage = `url("${mapDefinition.tileset.imageUrl}")`;
      tile.style.backgroundSize = `${tilesetColumns * tileSize}px ${tilesetRows * tileSize}px`;
      mapLayer.appendChild(tile);
      tileNodes.push(tile);
    });
  });

  const waterCanvas = document.createElement("canvas");
  waterCanvas.className = "map-water-flow-canvas";
  waterCanvas.setAttribute("aria-hidden", "true");
  waterCanvas.width = Math.max(1, mapDefinition.renderWidth * tileSize + WATER_FLOW_SHIFT_PX);
  waterCanvas.height = Math.max(1, mapDefinition.renderHeight * tileSize);
  waterCanvas.style.left = `${-WATER_FLOW_SHIFT_PX}px`;
  waterCanvas.style.width = `${waterCanvas.width}px`;
  waterCanvas.style.height = `${waterCanvas.height}px`;
  mapLayer.appendChild(waterCanvas);

  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  renderableMapObjects(mapDefinition, saveEnvelope).forEach((row, index) => {
    const marker = document.createElement("div");
    marker.className = `map-object${row?.type === "npc" ? " map-object-npc" : ""}${row?.type !== "npc" && row?.spriteImageUrl ? " map-object-image" : ""}`;
    if (row?.type === "npc") {
      marker.style.left = "0px";
      marker.style.top = "0px";
      marker.style.transform = npcTileTransform(row, renderPadding, tileSize);
    } else {
      marker.style.left = `${(Number(row.x || 0) + renderPadding.left) * tileSize}px`;
      marker.style.top = `${(Number(row.y || 0) + renderPadding.top) * tileSize}px`;
    }
    marker.title = String(row?.name || row?.type || "");
    if (row?.type === "npc" && row?.spriteImageUrl) {
      marker.innerHTML = `<span class="map-npc-sprite" aria-hidden="true"></span>`;
      marker.dataset.npcKey = npcObjectKey(row, index);
      const npcSprite = marker.querySelector(".map-npc-sprite");
      npcSprite?.style.setProperty("--npc-sprite-url", `url("${row.spriteImageUrl}")`);
      npcSprite?.setAttribute("data-npc-key", marker.dataset.npcKey);
    } else if (row?.spriteImageUrl) {
      marker.innerHTML = `<span class="map-object-sprite" aria-hidden="true"></span>`;
      const objectSprite = marker.querySelector(".map-object-sprite");
      const frameCount = resolveObjectSpriteFrameCount(row);
      const frameMs = resolveObjectSpriteFrameMs(row);
      objectSprite?.style.setProperty("--object-sprite-url", `url("${row.spriteImageUrl}")`);
      objectSprite?.style.setProperty("--object-frame-count", String(frameCount));
      if (frameCount > 1 && row?.sprite_animate !== false) {
        objectSprite?.classList.add("is-animated");
        objectSprite?.style.setProperty("animation-duration", `${frameCount * frameMs}ms`);
      }
    } else {
      marker.innerHTML = `<span>${objectLabel(row?.type)}</span>`;
    }
    mapLayer.appendChild(marker);
  });

  const crystalOrigin = findCrystalSpriteOrigin(mapDefinition);
  if (crystalOrigin) {
    const crystal = document.createElement("div");
    crystal.className = "map-decoration map-decoration-crystal";
    crystal.setAttribute("aria-hidden", "true");
    crystal.style.left = `${(crystalOrigin.x + renderPadding.left) * tileSize}px`;
    crystal.style.top = `${(crystalOrigin.y + renderPadding.top) * tileSize}px`;
    mapLayer.appendChild(crystal);
  }

  const nextState = {
    signature,
    tileNodes,
    waterCanvas,
    previousRenderRows: [],
    tilesetColumns,
  };
  mapRenderStateCache.set(mapLayer, nextState);
  return nextState;
}

function updateRenderedTile(tile, gid, tilesetColumns, mapDefinition) {
  if (!tile) return;
  const tileSize = DISPLAY_TILE_SIZE;
  const localId = Math.max(0, Number(gid || 0) - 1);
  const col = localId % tilesetColumns;
  const tileRow = Math.floor(localId / tilesetColumns);
  tile.style.backgroundPosition = `${-col * tileSize}px ${-tileRow * tileSize}px`;
  tile.dataset.gid = String(Number(gid || 0));
  tile.classList.toggle("map-tile-water", isWaterFlowTileGid(gid, mapDefinition));
  let waterHighlight = tile.querySelector(".map-water-highlight");
  if (isWaterAnimationGid(gid, mapDefinition) && !isWaterFlowTileGid(gid, mapDefinition)) {
    if (!waterHighlight) {
      waterHighlight = document.createElement("span");
      waterHighlight.className = "map-water-highlight";
      waterHighlight.setAttribute("aria-hidden", "true");
      tile.appendChild(waterHighlight);
    }
    waterHighlight.dataset.waterGid = String(Number(gid || 0));
  } else if (waterHighlight) {
    waterHighlight.remove();
  }
}

export function findStandingObject(mapDefinition, mapState, saveEnvelope = null) {
  return (mapDefinition?.objects || []).find((row) => (
    isMapObjectAvailable(row, saveEnvelope)
    && Number(row?.x) === Number(mapState?.tile_x)
    && Number(row?.y) === Number(mapState?.tile_y)
  )) || null;
}

export function findStandingEventTrigger(mapDefinition, mapState, saveEnvelope) {
  const hit = (mapDefinition?.objects || []).find((row) => (
    Number(row?.x) === Number(mapState?.tile_x) && Number(row?.y) === Number(mapState?.tile_y)
  )) || null;
  if (hit?.type !== "event") return null;
  if (!isMapObjectAvailable(hit, saveEnvelope)) return null;
  return hit;
}

export function findAdjacentObject(mapDefinition, mapState, predicate = () => true, saveEnvelope = null) {
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  const facingDirection = normalizeMapFacingDirection(mapState?.facing_direction, "down");
  const delta = directionDelta(facingDirection);
  if (!delta) return null;
  const targetX = tileX + delta.x;
  const targetY = tileY + delta.y;
  return (mapDefinition?.objects || []).find((row) => {
    const objectX = Number(row?.x);
    const objectY = Number(row?.y);
    return isMapObjectAvailable(row, saveEnvelope) && objectX === targetX && objectY === targetY && predicate(row);
  }) || null;
}

export function findAdjacentNpc(mapDefinition, mapState, saveEnvelope = null) {
  return findAdjacentObject(
    mapDefinition,
    mapState,
    (row) => row?.type === "npc" && npcDialogueIndices(row).length > 0,
    saveEnvelope,
  );
}

export function findAdjacentTileWithGid(mapDefinition, mapState, gid) {
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  const targetGid = Number(gid);
  const deltas = [
    { x: 0, y: -1 },
    { x: 0, y: 1 },
    { x: -1, y: 0 },
    { x: 1, y: 0 },
  ];
  return deltas.find((delta) => (
    Number(mapDefinition?.rows?.[tileY + delta.y]?.[tileX + delta.x] ?? NaN) === targetGid
  )) || null;
}

export function findShopActivation(mapDefinition, mapState) {
  const mapId = String(mapDefinition?.id || mapState?.current_map_id || "");
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  return MAP_SHOP_ACTIVATIONS.find((row) => (
    row.mapId === mapId
    && Math.abs(tileX - Number(row.x)) + Math.abs(tileY - Number(row.y)) === 1
  )) || null;
}

export function isAdjacentToTileCoordinate(mapState, coordinate) {
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  const targetX = Number(coordinate?.x);
  const targetY = Number(coordinate?.y);
  return Math.abs(tileX - targetX) + Math.abs(tileY - targetY) === 1;
}

export function isFacingTileCoordinate(mapState, coordinate) {
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  const facingDirection = normalizeMapFacingDirection(mapState?.facing_direction, "down");
  const delta = directionDelta(facingDirection);
  if (!delta) return false;
  return (
    tileX + Number(delta.x || 0) === Number(coordinate?.x)
    && tileY + Number(delta.y || 0) === Number(coordinate?.y)
  );
}

export function isStandingOnTileCoordinate(mapState, coordinate) {
  return (
    Number(mapState?.tile_x) === Number(coordinate?.x)
    && Number(mapState?.tile_y) === Number(coordinate?.y)
  );
}

export function isUrInnItemShopRecoveryTile(mapDefinition, mapState) {
  if (String(mapDefinition?.id || mapState?.current_map_id || "") !== UR_INN_ITEMSHOP_MAP_ID) {
    return false;
  }
  return UR_INN_ITEMSHOP_RECOVERY_TILES.some((coordinate) => (
    isStandingOnTileCoordinate(mapState, coordinate)
  ));
}

export function isKazusInnItemShopRecoveryTile(mapDefinition, mapState) {
  if (String(mapDefinition?.id || mapState?.current_map_id || "") !== KAZUS_INN_ITEMSHOP_2F_MAP_ID) {
    return false;
  }
  return KAZUS_INN_ITEMSHOP_2F_RECOVERY_TILES.some((coordinate) => (
    isStandingOnTileCoordinate(mapState, coordinate)
  ));
}

export function isCastleSasuneMainKeep1FRecoveryTile(mapDefinition, mapState) {
  if (String(mapDefinition?.id || mapState?.current_map_id || "") !== CASTLE_SASUNE_MAINKEEP_1F_MAP_ID) {
    return false;
  }
  return CASTLE_SASUNE_MAINKEEP_1F_RECOVERY_TILES.some((coordinate) => (
    isStandingOnTileCoordinate(mapState, coordinate)
  ));
}

export function isCastleSasuneTowerEast4FRecoveryTile(mapDefinition, mapState) {
  if (String(mapDefinition?.id || mapState?.current_map_id || "") !== CASTLE_SASUNE_TOWER_EAST_4F_MAP_ID) {
    return false;
  }
  return CASTLE_SASUNE_TOWER_EAST_4F_RECOVERY_TILES.some((coordinate) => (
    isStandingOnTileCoordinate(mapState, coordinate)
  ));
}

function withoutKoStatusIcons(value) {
  return Array.isArray(value)
    ? value.filter((icon) => String(icon || "").trim().toLowerCase().replace(/[_-]/g, " ") !== "ko")
    : [];
}

function clearKoStatusEffects(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;
  return {
    ...value,
    KO: false,
  };
}

export function reviveZeroHpPartyMembersToOneHp(save, menuState) {
  let saveRevivedCount = 0;
  let menuRevivedCount = 0;
  const saveParty = Array.isArray(save?.party) ? save.party : [];
  saveParty.forEach((member) => {
    if (!member || typeof member !== "object") return;
    if (Number(member.hp ?? 0) > 0) return;
    member.hp = 1;
    member.status_icons = withoutKoStatusIcons(member.status_icons);
    member.status_effects = clearKoStatusEffects(member.status_effects);
    saveRevivedCount += 1;
  });

  const menuParty = Array.isArray(menuState?.party) ? menuState.party : [];
  menuParty.forEach((member) => {
    if (!member || typeof member !== "object") return;
    if (Number(member.hp ?? 0) > 0) return;
    member.hp = 1;
    menuRevivedCount += 1;
    member.status_icons = withoutKoStatusIcons(member.status_icons);
    if (member.status && typeof member.status === "object") {
      const statusIcons = withoutKoStatusIcons(member.status.status_icons);
      member.status = {
        ...member.status,
        hp: 1,
        status_icons: statusIcons,
        status_line: statusIcons.length ? statusIcons.join("/") : "-",
      };
    }
  });

  if (save && typeof save === "object") save.party = saveParty;
  if (menuState && typeof menuState === "object") menuState.party = menuParty;
  return Math.max(saveRevivedCount, menuRevivedCount);
}

export function findCrystalSpriteOrigin(mapDefinition) {
  if (String(mapDefinition?.id || "") !== ALTER_CAVE_CRYSTAL_ROOM_MAP_ID) return null;
  for (let y = 0; y < Number(mapDefinition?.height || 0) - 1; y += 1) {
    for (let x = 0; x < Number(mapDefinition?.width || 0); x += 1) {
      const topGid = Number(mapDefinition?.rows?.[y]?.[x] ?? NaN);
      const bottomGid = Number(mapDefinition?.rows?.[y + 1]?.[x] ?? NaN);
      if (topGid === 125 && bottomGid === 7) {
        return { x, y };
      }
    }
  }
  return null;
}

export function isAdjacentToCrystalSprite(mapDefinition, mapState) {
  const origin = findCrystalSpriteOrigin(mapDefinition);
  if (!origin) return false;
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  return (
    Math.abs(tileX - origin.x) + Math.abs(tileY - origin.y) === 1
    || Math.abs(tileX - origin.x) + Math.abs(tileY - (origin.y + 1)) === 1
  );
}

function describeStandingObject(mapDefinition, mapState) {
  const hit = findStandingObject(mapDefinition, mapState);
  if (!hit) return "";
  if (hit.type === "event") return "";
  if (hit.type === "exit") {
    return `出口: ${hit.name || hit.target_map || "-"}`;
  }
  if (hit.type === "switch") {
    return `スイッチ: ${hit.name || hit.switch_id || "-"}`;
  }
  if (hit.type === "chest") {
    return `宝箱: ${hit.name || "Treasure"}`;
  }
  return `オブジェクト: ${hit.name || hit.type || "-"}`;
}

function renderMapTiles(mapLayer, mapDefinition, saveEnvelope = null) {
  const renderRows = Array.isArray(mapDefinition?.renderRows) ? mapDefinition.renderRows : [];
  const renderState = ensureMapRenderState(mapLayer, mapDefinition, saveEnvelope);
  const previousRows = renderState.previousRenderRows;
  let tileIndex = 0;

  renderRows.forEach((row, y) => {
    row.forEach((gid, x) => {
      const previousGid = Number(previousRows?.[y]?.[x] ?? NaN);
      const nextGid = Number(gid || 0);
      if (previousGid !== nextGid) {
        updateRenderedTile(renderState.tileNodes[tileIndex], nextGid, renderState.tilesetColumns, mapDefinition);
      }
      tileIndex += 1;
    });
  });

  renderState.previousRenderRows = renderRows.map((row) => row.slice());
  scheduleWaterHighlightMasks(mapLayer, mapDefinition, renderState.signature);
}

export function applySwitchStateToMap(mapDefinition, switchStates = {}) {
  const normalizedSwitchStates = normalizeSwitchStates(switchStates);
  const normalizedOpenedTreasures = normalizeTreasureStates(mapDefinition?.openedTreasures);
  const baseRows = Array.isArray(mapDefinition?.baseRows) ? mapDefinition.baseRows : mapDefinition?.rows;
  const nextRows = Array.isArray(baseRows) ? baseRows.map((row) => row.slice()) : [];

  (mapDefinition?.objects || []).forEach((row) => {
    if (row?.type !== "barrier" || !row?.trigger_by) return;
    if (!normalizedSwitchStates[String(row.trigger_by)]) return;
    const x = Number(row?.x);
    const y = Number(row?.y);
    if (!Array.isArray(nextRows[y])) return;
    const closedGid = Number(row?.closed_gid || 49);
    const openGid = Number(row?.open_gid || 1);
    const current = Number(nextRows[y][x] ?? 0);
    if (current === closedGid) nextRows[y][x] = openGid;
    else if (current === openGid) nextRows[y][x] = closedGid;
  });

  (mapDefinition?.objects || []).forEach((row) => {
    if (row?.type !== "treasure") return;
    const key = treasureKey(row);
    if (!normalizedOpenedTreasures[key]) return;
    const x = Number(row?.x);
    const y = Number(row?.y);
    const closedGid = Number(row?.closed_gid || 125);
    const openGid = Number(row?.open_gid || 126);
    if (!Array.isArray(nextRows[y])) return;
    if (Number(nextRows[y][x] ?? 0) === closedGid) {
      nextRows[y][x] = openGid;
    }
  });

  const renderPadding = mapDefinition?.renderPadding || { top: 0, right: 0, bottom: 0, left: 0, fillGid: 0 };
  return {
    ...mapDefinition,
    rows: nextRows,
    openedTreasures: normalizedOpenedTreasures,
    renderRows: buildRenderRows(nextRows, mapDefinition.width, mapDefinition.height, {
      top: renderPadding.top,
      right: renderPadding.right,
      bottom: renderPadding.bottom,
      left: renderPadding.left,
      fill_gid: renderPadding.fillGid,
    }),
  };
}

export function toggleAdjacentSwitch(mapDefinition, mapState) {
  const adjacentSwitch = findAdjacentObject(
    mapDefinition,
    mapState,
    (row) => row?.type === "switch" && row?.switch_id,
  );
  if (!adjacentSwitch) {
    return { toggled: false, mapDefinition, mapState };
  }
  const switchId = String(adjacentSwitch.switch_id);
  const currentSwitchStates = normalizeSwitchStates(mapState?.switch_states);
  const nextSwitchStates = {
    ...currentSwitchStates,
    [switchId]: !currentSwitchStates[switchId],
  };
  return {
    toggled: true,
    switchId,
    enabled: nextSwitchStates[switchId],
    mapDefinition: applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: normalizeTreasureStates(mapState?.opened_treasures) },
      nextSwitchStates,
    ),
    mapState: {
      ...mapState,
      switch_states: nextSwitchStates,
    },
  };
}

export function openAdjacentTreasure(mapDefinition, mapState, saveEnvelope, spellLevelByName = {}) {
  const adjacentTreasure = findAdjacentObject(
    mapDefinition,
    mapState,
    (row) => row?.type === "treasure",
  );
  if (!adjacentTreasure) {
    return { opened: false, mapDefinition, mapState, saveEnvelope };
  }
  const key = treasureKey(adjacentTreasure);
  const currentOpenedTreasures = normalizeTreasureStates(mapState?.opened_treasures);
  if (currentOpenedTreasures[key]) {
    return { opened: false, alreadyOpened: true, mapDefinition, mapState, saveEnvelope };
  }
  const guardedEnemyNames = normalizeGuardedEnemyNames(adjacentTreasure.guarded_by);
  if (guardedEnemyNames.length) {
    return {
      opened: false,
      guardedBattle: true,
      itemName: String(adjacentTreasure.item_name || "Potion"),
      enemyNames: guardedEnemyNames,
      pendingTreasureContext: {
        map_id: String(mapState?.current_map_id || mapDefinition?.id || ""),
        treasure_key: key,
      },
      mapDefinition,
      mapState,
      saveEnvelope,
    };
  }
  return finalizeTreasureOpen(
    mapDefinition,
    mapState,
    saveEnvelope,
    adjacentTreasure,
    spellLevelByName,
  );
}

function finalizeTreasureOpen(mapDefinition, mapState, saveEnvelope, treasureRow, inventoryResolverData = {}) {
  const key = treasureKey(treasureRow);
  const currentOpenedTreasures = normalizeTreasureStates(mapState?.opened_treasures);
  if (currentOpenedTreasures[key]) {
    return { opened: false, alreadyOpened: true, mapDefinition, mapState, saveEnvelope };
  }
  const nextOpenedTreasures = {
    ...currentOpenedTreasures,
    [key]: true,
  };
  const itemName = String(treasureRow.item_name || "Potion");
  const requestedBucketName = String(treasureRow.inventory_bucket || "Anywhere");
  const quantity = Math.max(1, asNumber(treasureRow.quantity, 1));
  const normalizedInventoryResolverData = (
    inventoryResolverData
    && typeof inventoryResolverData === "object"
    && (
      "spellLevelByName" in inventoryResolverData
      || "itemTypeByName" in inventoryResolverData
      || "weaponNameSet" in inventoryResolverData
      || "armorNameSet" in inventoryResolverData
    )
  )
    ? inventoryResolverData
    : { spellLevelByName: inventoryResolverData || {} };
  const spellLevelByName = normalizedInventoryResolverData.spellLevelByName || {};
  const bucketName = itemName === "GIL"
    ? requestedBucketName
    : resolveInventoryBucketForItem(normalizedInventoryResolverData, itemName, requestedBucketName);
  const nextEnvelope = typeof structuredClone === "function"
    ? structuredClone(saveEnvelope || { save: {} })
    : JSON.parse(JSON.stringify(saveEnvelope || { save: {} }));
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = {};
  }
  if (itemName === "GIL") {
    nextEnvelope.save.gil = Math.max(0, asNumber(nextEnvelope.save.gil, 0)) + quantity;
    if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
      nextEnvelope.menu_state = {};
    }
    if (!nextEnvelope.menu_state.resources || typeof nextEnvelope.menu_state.resources !== "object") {
      nextEnvelope.menu_state.resources = { cp: 0, cp_max: 255, gil: 0 };
    }
    nextEnvelope.menu_state.resources.gil = Math.max(0, asNumber(nextEnvelope.menu_state.resources.gil, 0)) + quantity;
  } else if (!addItemToInventory(nextEnvelope.save, bucketName, itemName, quantity, spellLevelByName)) {
    return {
      opened: false,
      inventoryError: true,
      itemName,
      bucketName,
      mapDefinition,
      mapState,
      saveEnvelope,
    };
  }
  return {
    opened: true,
    itemName,
    quantity,
    mapDefinition: applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: nextOpenedTreasures },
      mapState?.switch_states,
    ),
    mapState: {
      ...mapState,
      opened_treasures: nextOpenedTreasures,
    },
    saveEnvelope: writeSavedTreasureStates(nextEnvelope, mapState?.current_map_id || mapDefinition?.id, nextOpenedTreasures),
  };
}

function treasureGainStatusText(treasureResult) {
  const itemName = String(treasureResult?.itemName || "");
  const quantity = Math.max(1, asNumber(treasureResult?.quantity, 1));
  if (itemName === "GIL") {
    return `${quantity} GIL を手に入れた！`;
  }
  return `${itemName} を手に入れた！`;
}

export function applyPendingGuardedTreasureReward(
  mapDefinition,
  mapState,
  saveEnvelope,
  pendingTreasureContext,
  spellLevelByName = {},
) {
  const pendingMapId = String(pendingTreasureContext?.map_id || "");
  const currentMapId = String(mapState?.current_map_id || mapDefinition?.id || "");
  if (!pendingMapId || pendingMapId !== currentMapId) {
    return { opened: false, mapDefinition, mapState, saveEnvelope };
  }
  const treasure = findTreasureByKey(mapDefinition, pendingTreasureContext?.treasure_key);
  if (!treasure) {
    return { opened: false, missingTreasure: true, mapDefinition, mapState, saveEnvelope };
  }
  return finalizeTreasureOpen(mapDefinition, mapState, saveEnvelope, treasure, spellLevelByName);
}

function updateViewportTransform(mapViewport, mapLayer, mapDefinition, mapState, visualPosition = null) {
  const viewportWidth = mapViewport.clientWidth;
  const viewportHeight = mapViewport.clientHeight;
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  const mapPixelWidth = mapDefinition.renderWidth * DISPLAY_TILE_SIZE;
  const mapPixelHeight = mapDefinition.renderHeight * DISPLAY_TILE_SIZE;
  const viewX = asNumber(visualPosition?.x, mapState?.tile_x);
  const viewY = asNumber(visualPosition?.y, mapState?.tile_y);
  const centeredX = viewportWidth / 2 - (viewX + renderPadding.left + 0.5) * DISPLAY_TILE_SIZE;
  const centeredY = viewportHeight / 2 - (viewY + renderPadding.top + 0.5) * DISPLAY_TILE_SIZE;
  const minX = Math.min(0, viewportWidth - mapPixelWidth);
  const minY = Math.min(0, viewportHeight - mapPixelHeight);
  const translateX = clamp(centeredX, minX, 0);
  const translateY = clamp(centeredY, minY, 0);
  mapLayer.style.transform = `translate(${translateX}px, ${translateY}px)`;
  return {
    translateX,
    translateY,
    viewX,
    viewY,
  };
}

function updateMapPlayerSprite(mapPlayer, direction, walkFrame) {
  if (!mapPlayer) return;
  const { frameIndex, facingScale } = resolveCharacterSpriteFrame(direction, walkFrame);
  mapPlayer.style.backgroundPosition = `${-frameIndex * CHARACTER_DISPLAY_TILE_SIZE}px 0`;
  mapPlayer.style.setProperty("--player-facing-scale", String(facingScale));
}

export function resolveCanoeSpriteFrame(direction, walkFrame = 0) {
  const normalizedDirection = normalizeMapFacingDirection(direction, "down");
  const frameOffset = Math.abs(Number(walkFrame || 0)) % 2;
  if (normalizedDirection === "left" || normalizedDirection === "right") {
    return { frameIndex: frameOffset, facingScale: 1 };
  }
  return { frameIndex: 2 + frameOffset, facingScale: 1 };
}

export function resolveAirshipUpperSprite(direction) {
  const normalizedDirection = normalizeMapFacingDirection(direction, "left");
  switch (normalizedDirection) {
    case "up":
      return { startFrame: 2, endFrame: 3, facingScale: 1 };
    case "down":
      return { startFrame: 6, endFrame: 7, facingScale: 1 };
    case "right":
      return { startFrame: 4, endFrame: 5, facingScale: -1 };
    case "left":
    default:
      return { startFrame: 4, endFrame: 5, facingScale: 1 };
  }
}

function updateNpcSpriteFrame(node, direction, walkFrame) {
  if (!node) return;
  const frameIndex = resolveNpcSpriteFrame(direction, walkFrame);
  node.style.backgroundPosition = `${-frameIndex * NPC_DISPLAY_TILE_SIZE}px 0`;
  node.style.transform = `scaleX(${resolveNpcFacingScale(direction)})`;
}

export function isPlayerInCanoe(mapDefinition, mapState, saveEnvelope = null) {
  if (
    !mapDefinition
    || !mapState
    || isAirshipRiding(mapDefinition, mapState, saveEnvelope)
    || !isFloatingContinentCanoeEnabled(mapDefinition, saveEnvelope)
  ) {
    return false;
  }
  const gid = Number(mapDefinition.rows?.[Number(mapState?.tile_y) || 0]?.[Number(mapState?.tile_x) || 0] ?? 0);
  return isCanoeWaterGid(gid);
}

export function shouldRenderGuestFollowerOnMap(mapDefinition, mapState, saveEnvelope = null, options = {}) {
  const followerType = resolveActiveGuestFollowerType(saveEnvelope, options);
  if (!followerType) {
    return false;
  }
  if (isAirshipRiding(mapDefinition, mapState, saveEnvelope)) {
    return false;
  }
  if (isPlayerInCanoe(mapDefinition, mapState, saveEnvelope)) {
    return false;
  }
  return true;
}

function updateMapPlayerSpriteImage(mapPlayer, mapDefinition, mapState, appState) {
  if (!mapPlayer) return;
  if (isPlayerInCanoe(mapDefinition, mapState, appState?.saveEnvelope)) {
    mapPlayer.style.setProperty("--player-sprite-url", `url("${CANOE_IMAGE_URL}")`);
    mapPlayer.style.setProperty("--player-sprite-rows", "1");
    mapPlayer.style.setProperty("--player-sprite-columns", String(CANOE_SPRITE_COLUMNS));
    return;
  }
  const sprite = resolveLeaderCharacterSprite(appState);
  mapPlayer.style.setProperty("--player-sprite-url", `url("${sprite.url}")`);
  mapPlayer.style.setProperty("--player-sprite-rows", String(sprite.rows));
  mapPlayer.style.setProperty("--player-sprite-columns", String(CHARACTER_SHEET_COLUMNS));
}

function updateMapPlayerSpriteForState(mapPlayer, direction, walkFrame, mapDefinition, mapState, saveEnvelope = null) {
  if (!mapPlayer) return;
  const spriteFrame = isPlayerInCanoe(mapDefinition, mapState, saveEnvelope)
    ? resolveCanoeSpriteFrame(direction, walkFrame)
    : resolveCharacterSpriteFrame(direction, walkFrame);
  mapPlayer.style.backgroundPosition = `${-spriteFrame.frameIndex * CHARACTER_DISPLAY_TILE_SIZE}px 0`;
  mapPlayer.style.setProperty("--player-facing-scale", String(spriteFrame.facingScale));
}

function updateMapPlayerVisibility(mapPlayer, mapDefinition, mapState, saveEnvelope = null) {
  if (!mapPlayer) return;
  mapPlayer.style.display = isAirshipRiding(mapDefinition, mapState, saveEnvelope) ? "none" : "block";
}

function updateMapPlayerPosition(mapPlayer, mapDefinition, viewportTransform) {
  if (!mapPlayer) return;
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  const translateX = Number(viewportTransform?.translateX || 0);
  const translateY = Number(viewportTransform?.translateY || 0);
  const viewX = Number(viewportTransform?.viewX || 0);
  const viewY = Number(viewportTransform?.viewY || 0);
  const playerLeft = translateX + (viewX + renderPadding.left + 0.5) * DISPLAY_TILE_SIZE;
  const playerTop = translateY + (viewY + renderPadding.top + 0.5) * DISPLAY_TILE_SIZE;
  mapPlayer.style.setProperty("--player-left", `${playerLeft}px`);
  mapPlayer.style.setProperty("--player-top", `${playerTop}px`);
}

function ensureAirshipNode(mapLayer, className) {
  let node = mapLayer.querySelector(`.${className}`);
  if (!node) {
    node = document.createElement("div");
    node.className = `map-airship ${className}`;
    node.setAttribute("aria-hidden", "true");
    mapLayer.appendChild(node);
  }
  return node;
}

function updateFloatingContinentAirship(
  mapLayer,
  mapDefinition,
  mapState,
  saveEnvelope = null,
  visualPosition = null,
  options = {},
) {
  const existingNodes = mapLayer.querySelectorAll(".map-airship");
  const available = isFloatingContinentAirshipEnabled(mapDefinition, saveEnvelope);
  if (
    options?.suppressAirship === true
    || !available
    || !Number.isFinite(Number(mapState?.airship_tile_x))
    || !Number.isFinite(Number(mapState?.airship_tile_y))
  ) {
    existingNodes.forEach((node) => node.remove());
    return;
  }
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  if (isAirshipRiding(mapDefinition, mapState, saveEnvelope)) {
    const viewX = asNumber(visualPosition?.x, mapState?.airship_tile_x);
    const viewY = asNumber(visualPosition?.y, mapState?.airship_tile_y);
    const left = (viewX + Number(renderPadding.left || 0)) * DISPLAY_TILE_SIZE;
    const top = (viewY + Number(renderPadding.top || 0)) * DISPLAY_TILE_SIZE;
    const upperSprite = resolveAirshipUpperSprite(mapState?.facing_direction);
    existingNodes.forEach((node) => {
      if (!node.classList.contains("map-airship-lower") && !node.classList.contains("map-airship-upper")) {
        node.remove();
      }
    });
    const lower = ensureAirshipNode(mapLayer, "map-airship-lower");
    const upper = ensureAirshipNode(mapLayer, "map-airship-upper");
    lower.style.left = `${left}px`;
    lower.style.top = `${top}px`;
    upper.style.left = `${left}px`;
    upper.style.top = `${top - DISPLAY_TILE_SIZE}px`;
    upper.style.setProperty("--airship-upper-start-frame", String(-upperSprite.startFrame));
    upper.style.setProperty("--airship-upper-end-frame", String(-(upperSprite.endFrame + 1)));
    upper.style.setProperty("--airship-facing-scale", String(upperSprite.facingScale));
    return;
  }
  existingNodes.forEach((node) => {
    if (!node.classList.contains("map-airship-ground")) {
      node.remove();
    }
  });
  const left = (Number(mapState.airship_tile_x) + Number(renderPadding.left || 0)) * DISPLAY_TILE_SIZE;
  const top = (Number(mapState.airship_tile_y) + Number(renderPadding.top || 0)) * DISPLAY_TILE_SIZE;
  const ground = ensureAirshipNode(mapLayer, "map-airship-ground");
  ground.style.left = `${left}px`;
  ground.style.top = `${top}px`;
}

function removeAirshipCrashNodes(mapLayer) {
  if (!mapLayer) return;
  mapLayer.querySelectorAll(".map-airship-crash-piece, .map-airship-crash-burst").forEach((node) => node.remove());
}

function stopAirshipCrashAnimation(mapLayer) {
  if (activeAirshipCrashAnimationFrameId !== null) {
    cancelAnimationFrame(activeAirshipCrashAnimationFrameId);
    activeAirshipCrashAnimationFrameId = null;
  }
  removeAirshipCrashNodes(mapLayer);
}

async function playAirshipCrashAnimation(mapLayer, mapDefinition, tileX, tileY, durationMs = AIRSHIP_CRASH_DURATION_MS) {
  if (!mapLayer || !mapDefinition) return false;
  stopAirshipCrashAnimation(mapLayer);
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  const anchorLeft = (Number(tileX || 0) + Number(renderPadding.left || 0)) * DISPLAY_TILE_SIZE;
  const anchorTop = (Number(tileY || 0) + Number(renderPadding.top || 0)) * DISPLAY_TILE_SIZE;
  const pieceConfigs = [
    { dx: -3.4, dy: -1.8, rotation: -260, delay: 0.00, clipPath: "polygon(0 0, 58% 0, 44% 48%, 0 42%)" },
    { dx: 3.2, dy: -1.4, rotation: 230, delay: 0.03, clipPath: "polygon(42% 0, 100% 0, 100% 44%, 58% 52%)" },
    { dx: -2.8, dy: 0.4, rotation: -190, delay: 0.06, clipPath: "polygon(0 40%, 48% 46%, 42% 100%, 0 100%)" },
    { dx: 2.9, dy: 0.7, rotation: 210, delay: 0.08, clipPath: "polygon(54% 48%, 100% 42%, 100% 100%, 58% 100%)" },
    { dx: -1.0, dy: -2.6, rotation: -320, delay: 0.02, clipPath: "polygon(18% 18%, 82% 12%, 70% 60%, 26% 58%)" },
    { dx: 0.6, dy: 2.5, rotation: 280, delay: 0.10, clipPath: "polygon(24% 54%, 78% 50%, 72% 86%, 30% 88%)" },
  ];
  const burstConfigs = [
    { dx: -0.2, dy: -0.3, scale: 1.9, delay: 0.00 },
    { dx: 1.4, dy: -1.0, scale: 1.2, delay: 0.16 },
    { dx: -1.7, dy: 0.8, scale: 1.1, delay: 0.24 },
    { dx: 0.9, dy: 1.5, scale: 1.35, delay: 0.34 },
  ];
  const pieceNodes = pieceConfigs.map((config) => {
    const node = document.createElement("div");
    node.className = "map-airship-crash-piece";
    node.style.left = `${anchorLeft}px`;
    node.style.top = `${anchorTop}px`;
    node.style.clipPath = config.clipPath;
    mapLayer.appendChild(node);
    return { node, config };
  });
  const burstNodes = burstConfigs.map((config) => {
    const node = document.createElement("div");
    node.className = "map-airship-crash-burst";
    node.style.left = `${anchorLeft + (DISPLAY_TILE_SIZE * 0.05)}px`;
    node.style.top = `${anchorTop + (DISPLAY_TILE_SIZE * 0.05)}px`;
    mapLayer.appendChild(node);
    return { node, config };
  });
  const startedAt = performance.now();
  return new Promise((resolve) => {
    const tick = (frameNow) => {
      const elapsed = frameNow - startedAt;
      const progress = clamp(elapsed / Math.max(1, Number(durationMs || 0)), 0, 1);
      pieceNodes.forEach(({ node, config }) => {
        const localProgress = clamp((progress - config.delay) / Math.max(0.2, 1 - config.delay), 0, 1);
        const distance = localProgress * (1 + (localProgress * 0.8));
        const translateX = config.dx * DISPLAY_TILE_SIZE * distance;
        const translateY = (config.dy * DISPLAY_TILE_SIZE * localProgress) + (DISPLAY_TILE_SIZE * 1.6 * localProgress * localProgress);
        const opacity = 1 - clamp((localProgress - 0.58) / 0.42, 0, 1);
        node.style.opacity = `${opacity}`;
        node.style.transform = `translate(${translateX}px, ${translateY}px) rotate(${config.rotation * localProgress}deg) scale(${1 - (localProgress * 0.18)})`;
      });
      burstNodes.forEach(({ node, config }) => {
        const localProgress = clamp((progress - config.delay) / 0.28, 0, 1);
        const opacity = 1 - localProgress;
        node.style.opacity = `${opacity}`;
        node.style.transform = `translate(${config.dx * DISPLAY_TILE_SIZE * localProgress}px, ${config.dy * DISPLAY_TILE_SIZE * localProgress}px) scale(${config.scale * localProgress})`;
      });
      if (progress >= 1) {
        activeAirshipCrashAnimationFrameId = null;
        removeAirshipCrashNodes(mapLayer);
        resolve(true);
        return;
      }
      activeAirshipCrashAnimationFrameId = requestAnimationFrame(tick);
    };
    activeAirshipCrashAnimationFrameId = requestAnimationFrame(tick);
  });
}

function updateMeta(mapMeta, mapDefinition, mapState) {
  const standing = isAirshipRiding(mapDefinition, mapState)
    ? "飛空艇に搭乗中です。"
    : (isStandingOnAirship(mapDefinition, mapState) ? "飛空艇" : describeStandingObject(mapDefinition, mapState));
  mapMeta.innerHTML = [
    `<div>Map: ${mapDefinition.name}</div>`,
    `<div>座標: (${mapState.tile_x}, ${mapState.tile_y})</div>`,
    `<div>${standing || "足元に特別なオブジェクトはありません。"}</div>`,
  ].join("");
}

function readBattleReturnContext() {
  try {
    const raw = sessionStorage.getItem(BATTLE_RETURN_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function readMapEntryContext() {
  try {
    const raw = sessionStorage.getItem(MAP_ENTRY_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

export function shouldResumeMapPosition(appState, battleReturnContext = null) {
  if (battleReturnContext?.return_route === "map" && battleReturnContext?.resume_map) {
    return true;
  }
  return Boolean(appState?.menuState?.map_return_pending);
}

function isBattleReturnToMap(battleReturnContext) {
  return Boolean(
    battleReturnContext?.return_route === "map"
    && battleReturnContext?.resume_map,
  );
}

export function deriveMapLaunchContext(appState, battleReturnContext = null, mapEntryContext = null) {
  const freshLocationEntry = Boolean(
    mapEntryContext?.entry_route === "location"
    && mapEntryContext?.fresh_start,
  );
  const resumeFromSavedPosition = freshLocationEntry
    ? false
    : shouldResumeMapPosition(appState, battleReturnContext);
  const returningFromBattle = freshLocationEntry ? false : isBattleReturnToMap(battleReturnContext);
  const requestedMapId = String(
    (freshLocationEntry && mapEntryContext?.map_id)
    || (returningFromBattle && battleReturnContext?.map_id)
    || appState?.menuState?.map_state?.current_map_id
    || appState?.saveEnvelope?.save?.map?.map
    || DEFAULT_MAP_ID,
  );
  return {
    freshLocationEntry,
    resumeFromSavedPosition,
    returningFromBattle,
    requestedMapId,
  };
}

export function shouldCloseEventOverlayOnConfirm(isOverlayOpen) {
  return Boolean(isOverlayOpen);
}

export function resolveInitialMapSelection(appState, mapDefinition, options = {}) {
  const shouldPreferMapSelection = Boolean(
    options?.returningFromBattle || options?.resumeFromSavedPosition,
  );
  const fallbackSelection = {
    selected_location_group: appState?.selectedLocationGroup,
    selected_location: appState?.selectedLocation,
  };
  if (isFloatingContinentMap(mapDefinition)) {
    const mapState = (
      appState?.menuState?.map_state && typeof appState.menuState.map_state === "object"
        ? appState.menuState.map_state
        : appState?.saveEnvelope?.save?.map
    );
    return resolveFloatingContinentSelection(
      mapDefinition,
      fallbackSelection,
      shouldPreferMapSelection ? mapState : null,
      appState?.saveEnvelope,
    );
  }
  if (shouldPreferMapSelection) {
    return buildEncounterSelection(mapDefinition, {
      selected_location_group: fallbackSelection.selected_location_group,
      selected_location: fallbackSelection.selected_location,
    });
  }
  return fallbackSelection;
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const mapStatus = mountNode.querySelector("#mapStatus");
  const mapViewport = mountNode.querySelector("#mapViewport");
  const mapLayer = mountNode.querySelector("#mapLayer");
  const mapPlayer = mountNode.querySelector(".map-player");
  const mapMeta = mountNode.querySelector("#mapMeta");
  const confirmBtn = mountNode.querySelector("#confirmBtn");
  const cancelBtn = mountNode.querySelector("#cancelBtn");
  const locationBtn = mountNode.querySelector("#locationBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");
  const battleBtn = mountNode.querySelector("#battleBtn");
  const mapFlash = mountNode.querySelector("#mapFlash");
  const mapEventOverlay = mountNode.querySelector("#mapEventOverlay");
  const mapEventText = mountNode.querySelector("#mapEventText");
  const mapEventCloseBtn = mountNode.querySelector("#mapEventCloseBtn");
  const padButtons = Array.from(mountNode.querySelectorAll("[data-dir]"));

  let mapDefinition = null;
  let mapState = null;
  let resizeObserver = null;
  let encounterLocked = false;
  let mapTransitionLocked = false;
  let spellLevelByName = {};
  let suppressFloatingContinentAirship = false;
  let pyodide = null;
  let eventOverlayCloseAction = null;
  let visualMapPosition = null;
  let moveAnimationFrameId = null;
  let moveAnimation = null;
  let npcAnimationIntervalId = null;
  let playerDirection = "down";
  let playerWalkFrame = 0;
  let mapBgmAudio = null;
  let currentMapBgmUrl = "";
  let cancelPendingBgmUnlock = null;
  let saraFollowerState = null;
  let saraFollowerDialogueCount = 0;
  let visualSaraFollowerPosition = null;
  let saraFollowerMoveAnimation = null;
  let saraFollowerMoveAnimationFrameId = null;
  let forceSaraFollowerVisible = false;
  let cutsceneRingNode = null;
  let cutsceneRingAnimation = null;
  let cutsceneRingAnimationFrameId = null;
  const npcAnimationStates = new Map();
  const holdRepeater = createDirectionalHoldRepeater((direction) => tryMove(direction));

  function findNpcMarkerByKey(npcKey) {
    const escapedKey = typeof CSS !== "undefined" && typeof CSS.escape === "function"
      ? CSS.escape(String(npcKey || ""))
      : String(npcKey || "").replace(/"/g, '\\"');
    return mapLayer.querySelector(`.map-object-npc[data-npc-key="${escapedKey}"]`);
  }

  function setNpcMarkerTransform(marker, row) {
    if (!marker || !row) return;
    const renderPadding = mapDefinition?.renderPadding || { left: 0, top: 0 };
    marker.style.transform = npcTileTransform(row, renderPadding);
  }

  function isSaraFollowerActive(saveEnvelope = store.getState().saveEnvelope) {
    return isSaraGuestActive(saveEnvelope);
  }

  function isCidFollowerActive(saveEnvelope = store.getState().saveEnvelope) {
    return isCidGuestActive(saveEnvelope);
  }

  function activeFollowerType(saveEnvelope = store.getState().saveEnvelope) {
    return resolveActiveGuestFollowerType(saveEnvelope, { forceSaraVisible: forceSaraFollowerVisible });
  }

  function shouldRenderSaraFollower(saveEnvelope = store.getState().saveEnvelope) {
    return shouldRenderGuestFollowerOnMap(
      mapDefinition,
      mapState,
      saveEnvelope,
      { forceSaraVisible: forceSaraFollowerVisible },
    );
  }

  function followerSpriteUrlForType(type) {
    if (type === "sara") {
      return new URL("../../assets/images/NPCs/fs_sara.png", import.meta.url).href;
    }
    if (type === "cid") {
      return new URL("../../assets/images/NPCs/fs_cid.png", import.meta.url).href;
    }
    return "";
  }

  function currentDialoguePartyMembers() {
    const party = Array.isArray(store.getState()?.menuState?.party)
      ? store.getState().menuState.party
      : Array.isArray(store.getState()?.saveEnvelope?.save?.party)
        ? store.getState().saveEnvelope.save.party
        : [];
    return party.slice(0, 4).map((member) => ({ ...member }));
  }

  function ensureSaraFollowerNode() {
    let node = mapLayer.querySelector(".map-follower");
    const followerType = activeFollowerType(store.getState().saveEnvelope);
    const spriteUrl = followerSpriteUrlForType(followerType);
    if (!node) {
      node = document.createElement("div");
      node.className = "map-follower";
      node.setAttribute("aria-hidden", "true");
      node.innerHTML = `<span class="map-npc-sprite" aria-hidden="true"></span>`;
      mapLayer.appendChild(node);
    }
    node.dataset.followerType = followerType;
    const sprite = node.querySelector(".map-npc-sprite");
    sprite?.style.setProperty("--npc-sprite-url", `url("${spriteUrl}")`);
    return node;
  }

  function hideSaraFollowerNode() {
    mapLayer.querySelector(".map-follower")?.remove();
  }

  function stopCutsceneRingAnimation() {
    if (cutsceneRingAnimationFrameId !== null) {
      cancelAnimationFrame(cutsceneRingAnimationFrameId);
      cutsceneRingAnimationFrameId = null;
    }
    cutsceneRingAnimation = null;
  }

  function ensureCutsceneRingNode() {
    if (!cutsceneRingNode) {
      cutsceneRingNode = document.createElement("div");
      cutsceneRingNode.className = "map-decoration map-decoration-ring";
      cutsceneRingNode.setAttribute("aria-hidden", "true");
      cutsceneRingNode.style.display = "none";
      mapLayer.appendChild(cutsceneRingNode);
    } else if (!cutsceneRingNode.isConnected) {
      mapLayer.appendChild(cutsceneRingNode);
    }
    return cutsceneRingNode;
  }

  function hideCutsceneRingNode() {
    stopCutsceneRingAnimation();
    if (cutsceneRingNode) {
      cutsceneRingNode.style.display = "none";
    }
  }

  function setCutsceneRingPosition(tileX, tileY, pixelOffsetX = 0, pixelOffsetY = 0) {
    const node = ensureCutsceneRingNode();
    const renderPadding = mapDefinition?.renderPadding || { left: 0, top: 0 };
    const left = (Number(tileX || 0) + Number(renderPadding.left || 0)) * DISPLAY_TILE_SIZE
      + (DISPLAY_TILE_SIZE / 2)
      + Number(pixelOffsetX || 0)
      - 2;
    const top = (Number(tileY || 0) + Number(renderPadding.top || 0)) * DISPLAY_TILE_SIZE
      + (DISPLAY_TILE_SIZE / 2)
      + Number(pixelOffsetY || 0)
      - 2;
    node.style.left = `${left}px`;
    node.style.top = `${top}px`;
    node.style.display = "block";
  }

  function stopSaraFollowerMoveAnimation() {
    if (saraFollowerMoveAnimationFrameId !== null) {
      cancelAnimationFrame(saraFollowerMoveAnimationFrameId);
      saraFollowerMoveAnimationFrameId = null;
    }
    saraFollowerMoveAnimation = null;
  }

  function setSaraFollowerVisualPosition(tileX, tileY) {
    stopSaraFollowerMoveAnimation();
    visualSaraFollowerPosition = {
      x: asNumber(tileX, 0),
      y: asNumber(tileY, 0),
    };
  }

  function animateSaraFollowerVisualPosition(previousPosition, nextPosition, durationMs = MAP_MOVE_ANIMATION_MS) {
    const now = performance.now();
    const fromPosition = resolveMapVisualPosition(
      visualSaraFollowerPosition,
      previousPosition,
    );
    const toPosition = resolveMapVisualPosition(null, nextPosition);
    stopSaraFollowerMoveAnimation();
    saraFollowerMoveAnimation = {
      fromPosition,
      toPosition,
      startedAt: now,
      durationMs: Math.max(1, Number(durationMs || 0)),
    };
    const tick = (frameNow) => {
      if (!saraFollowerMoveAnimation) return;
      const progress = (
        frameNow - saraFollowerMoveAnimation.startedAt
      ) / saraFollowerMoveAnimation.durationMs;
      visualSaraFollowerPosition = interpolateMapPosition(
        saraFollowerMoveAnimation.fromPosition,
        saraFollowerMoveAnimation.toPosition,
        progress,
      );
      redraw();
      if (progress >= 1) {
        visualSaraFollowerPosition = { ...saraFollowerMoveAnimation.toPosition };
        saraFollowerMoveAnimation = null;
        saraFollowerMoveAnimationFrameId = null;
        redraw();
        return;
      }
      saraFollowerMoveAnimationFrameId = requestAnimationFrame(tick);
    };
    saraFollowerMoveAnimationFrameId = requestAnimationFrame(tick);
  }

  function resolveSaraFollowerSpawnPosition(nextMapDefinition, nextMapState, saveEnvelope = store.getState().saveEnvelope) {
    const facing = normalizeMapFacingDirection(nextMapState?.facing_direction || playerDirection, "down");
    const reverseDirection = {
      up: "down",
      down: "up",
      left: "right",
      right: "left",
    }[facing] || "up";
    return {
      current_map_id: String(nextMapDefinition?.id || nextMapState?.current_map_id || ""),
      tile_x: Number(nextMapState?.tile_x || 0),
      tile_y: Number(nextMapState?.tile_y || 0),
      direction: reverseDirection,
      walkFrame: 0,
    };
  }

  function syncSaraFollowerStateForMap(nextMapDefinition, nextMapState, saveEnvelope = store.getState().saveEnvelope) {
    if (!shouldRenderGuestFollowerOnMap(
      nextMapDefinition,
      nextMapState,
      saveEnvelope,
      { forceSaraVisible: forceSaraFollowerVisible },
    )) {
      stopSaraFollowerMoveAnimation();
      visualSaraFollowerPosition = null;
      saraFollowerState = null;
      saraFollowerDialogueCount = 0;
      hideSaraFollowerNode();
      return;
    }
    if (
      saraFollowerState
      && saraFollowerState.current_map_id === String(nextMapDefinition?.id || "")
      && Number.isFinite(Number(saraFollowerState.tile_x))
      && Number.isFinite(Number(saraFollowerState.tile_y))
    ) {
      if (!visualSaraFollowerPosition) {
        setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
      }
      return;
    }
    saraFollowerState = resolveSaraFollowerSpawnPosition(nextMapDefinition, nextMapState, saveEnvelope);
    setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
  }

  function updateSaraFollowerNode() {
    if (!mapDefinition || !mapState || !shouldRenderSaraFollower(store.getState().saveEnvelope)) {
      hideSaraFollowerNode();
      return;
    }
    syncSaraFollowerStateForMap(mapDefinition, mapState, store.getState().saveEnvelope);
    if (!saraFollowerState) {
      hideSaraFollowerNode();
      return;
    }
    const node = ensureSaraFollowerNode();
    const renderPadding = mapDefinition?.renderPadding || { left: 0, top: 0 };
    const visualPosition = resolveMapVisualPosition(visualSaraFollowerPosition, {
      x: saraFollowerState.tile_x,
      y: saraFollowerState.tile_y,
    });
    node.style.transform = npcTileTransform({
      x: visualPosition.x,
      y: visualPosition.y,
    }, renderPadding);
    const sprite = node.querySelector(".map-npc-sprite");
    if (sprite) {
      updateNpcSpriteFrame(sprite, saraFollowerState.direction, saraFollowerState.walkFrame);
    }
    node.style.display = shouldRenderSaraFollower(store.getState().saveEnvelope) ? "block" : "none";
  }

  function tickSaraFollower() {
    if (!saraFollowerState || !shouldRenderSaraFollower(store.getState().saveEnvelope)) {
      hideSaraFollowerNode();
      return;
    }
    updateSaraFollowerNode();
  }

  function waitForDuration(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, Math.max(0, Number(ms || 0)));
    });
  }

  function openDialogueMessagesAndWait(messages) {
    const visibleMessages = Array.isArray(messages)
      ? messages.map((message) => String(message || "")).filter(Boolean)
      : [];
    if (!visibleMessages.length) return Promise.resolve(false);
    return new Promise((resolve) => {
      if (visibleMessages.length === 1) {
        openEventOverlay(visibleMessages[0], {
          onClose: () => resolve(true),
        });
        return;
      }
      openEventOverlaySequence(visibleMessages, {
        onComplete: () => resolve(true),
      });
    });
  }

  async function animateNpcStep(npcRow, npcState, marker, targetX, targetY, durationMs) {
    if (!npcRow || !npcState || !marker) return false;
    const fromX = Number(npcRow.x || 0);
    const fromY = Number(npcRow.y || 0);
    const deltaX = Number(targetX) - fromX;
    const deltaY = Number(targetY) - fromY;
    if (deltaX > 0) npcState.direction = "right";
    else if (deltaX < 0) npcState.direction = "left";
    else if (deltaY > 0) npcState.direction = "down";
    else if (deltaY < 0) npcState.direction = "up";
    npcRow.direction = npcState.direction;
    npcState.walkFrame = npcState.walkFrame === 0 ? 1 : 0;
    const spriteNode = marker.querySelector(".map-npc-sprite");
    if (spriteNode) updateNpcSpriteFrame(spriteNode, npcState.direction, npcState.walkFrame);
    marker.style.transitionDuration = `${Math.max(1, Number(durationMs || 0))}ms`;
    npcRow.x = Number(targetX);
    npcRow.y = Number(targetY);
    setNpcMarkerTransform(marker, npcRow);
    await waitForDuration(durationMs);
    npcState.walkFrame = 0;
    if (spriteNode) updateNpcSpriteFrame(spriteNode, npcState.direction, npcState.walkFrame);
    return true;
  }

  async function animatePlayerStepTo(targetX, targetY, durationMs) {
    if (!mapState) return false;
    const previousMapState = mapState;
    const nextX = Number(targetX);
    const nextY = Number(targetY);
    const deltaX = nextX - Number(previousMapState?.tile_x || 0);
    const deltaY = nextY - Number(previousMapState?.tile_y || 0);
    if (deltaX > 0) playerDirection = "right";
    else if (deltaX < 0) playerDirection = "left";
    else if (deltaY > 0) playerDirection = "down";
    else if (deltaY < 0) playerDirection = "up";
    playerWalkFrame = playerWalkFrame === 0 ? 1 : 0;
    mapState = {
      ...previousMapState,
      tile_x: nextX,
      tile_y: nextY,
      current_movement_plane: normalizeMovementPlane(previousMapState?.current_movement_plane, "ground"),
      facing_direction: playerDirection,
      steps_since_reset: asNumber(previousMapState?.steps_since_reset, 0) + 1,
    };
    animateVisualMapPosition(previousMapState, mapState);
    redraw();
    await waitForDuration(durationMs);
    playerWalkFrame = 0;
    redraw();
    return true;
  }

  async function animatePlayerStepToWithFacing(targetX, targetY, durationMs, facingDirection = "") {
    if (!mapState) return false;
    const previousFacing = playerDirection;
    const moved = await animatePlayerStepTo(targetX, targetY, durationMs);
    const resolvedFacing = normalizeMapFacingDirection(facingDirection, previousFacing);
    playerDirection = resolvedFacing;
    if (mapState) {
      mapState = {
        ...mapState,
        facing_direction: resolvedFacing,
      };
      redraw();
    }
    return moved;
  }

  async function animateSaraFollowerStepTo(targetX, targetY, durationMs) {
    if (!saraFollowerState) return false;
    const marker = ensureSaraFollowerNode();
    if (!marker) return false;
    const fromX = Number(saraFollowerState.tile_x || 0);
    const fromY = Number(saraFollowerState.tile_y || 0);
    const nextX = Number(targetX);
    const nextY = Number(targetY);
    let direction = normalizeNpcDirection(saraFollowerState.direction, "down");
    const deltaX = nextX - fromX;
    const deltaY = nextY - fromY;
    if (deltaX > 0) direction = "right";
    else if (deltaX < 0) direction = "left";
    else if (deltaY > 0) direction = "down";
    else if (deltaY < 0) direction = "up";
    saraFollowerState = {
      ...saraFollowerState,
      direction,
      walkFrame: saraFollowerState.walkFrame === 0 ? 1 : 0,
    };
    redraw();
    animateSaraFollowerVisualPosition({ x: fromX, y: fromY }, { x: nextX, y: nextY }, durationMs);
    await waitForDuration(durationMs);
    saraFollowerState = {
      ...saraFollowerState,
      current_map_id: String(mapDefinition?.id || saraFollowerState.current_map_id || ""),
      tile_x: nextX,
      tile_y: nextY,
      direction,
      walkFrame: 0,
    };
    setSaraFollowerVisualPosition(nextX, nextY);
    redraw();
    return true;
  }

  async function animateSaraFollowerStepToWithFacing(targetX, targetY, durationMs, facingDirection = "") {
    if (!saraFollowerState) return false;
    const previousFacing = normalizeNpcDirection(saraFollowerState.direction, "down");
    const moved = await animateSaraFollowerStepTo(targetX, targetY, durationMs);
    const resolvedFacing = normalizeNpcDirection(facingDirection, previousFacing);
    saraFollowerState = {
      ...saraFollowerState,
      direction: resolvedFacing,
      walkFrame: 0,
    };
    redraw();
    return moved;
  }

  async function animateCutsceneRingThrow(startTile, endTile, durationMs = 900) {
    if (!mapDefinition) return false;
    const startX = Number(startTile?.x);
    const startY = Number(startTile?.y);
    const endX = Number(endTile?.x);
    const endY = Number(endTile?.y);
    if (![startX, startY, endX, endY].every((value) => Number.isFinite(value))) {
      return false;
    }
    stopCutsceneRingAnimation();
    setCutsceneRingPosition(startX, startY, 0, -2);
    const startedAt = performance.now();
    const amplitudePx = DISPLAY_TILE_SIZE * 1.1;
    return new Promise((resolve) => {
      const tick = (frameNow) => {
        const progress = clamp((frameNow - startedAt) / Math.max(1, Number(durationMs || 0)), 0, 1);
        const currentTileX = startX + ((endX - startX) * progress);
        const currentTileY = startY + ((endY - startY) * progress);
        const arcOffsetY = -Math.sin(progress * Math.PI) * amplitudePx;
        setCutsceneRingPosition(currentTileX, currentTileY, 0, arcOffsetY - 2);
        if (progress >= 1) {
          cutsceneRingAnimationFrameId = null;
          cutsceneRingAnimation = null;
          resolve(true);
          return;
        }
        cutsceneRingAnimationFrameId = requestAnimationFrame(tick);
      };
      cutsceneRingAnimation = { startedAt, durationMs, startTile, endTile };
      cutsceneRingAnimationFrameId = requestAnimationFrame(tick);
    });
  }

  async function switchMapForCutscene(targetMapId, nextPlayerState = {}, options = {}) {
    const nextMapDefinition = await loadMapDefinition(String(targetMapId));
    const currentEnvelope = store.getState().saveEnvelope;
    const savedOpenedTreasures = readSavedTreasureStates(currentEnvelope, nextMapDefinition.id);
    mapDefinition = applySwitchStateToMap(
      { ...nextMapDefinition, openedTreasures: savedOpenedTreasures },
      normalizeSwitchStates(options?.switch_states),
    );
    mapState = {
      current_map_id: nextMapDefinition.id,
      tile_x: Number(nextPlayerState?.x ?? nextMapDefinition.spawn?.x ?? 0),
      tile_y: Number(nextPlayerState?.y ?? nextMapDefinition.spawn?.y ?? 0),
      current_movement_plane: normalizeMovementPlane(nextPlayerState?.current_movement_plane, "ground"),
      facing_direction: normalizeMapFacingDirection(nextPlayerState?.direction, playerDirection),
      steps_since_reset: 0,
      switch_states: normalizeSwitchStates(options?.switch_states),
      opened_treasures: savedOpenedTreasures,
    };
    playerDirection = normalizeMapFacingDirection(mapState.facing_direction, "down");
    playerWalkFrame = 0;
    if (options?.saraState) {
      saraFollowerState = {
        current_map_id: nextMapDefinition.id,
        tile_x: Number(options.saraState.x ?? mapState.tile_x),
        tile_y: Number(options.saraState.y ?? mapState.tile_y),
        direction: normalizeNpcDirection(options.saraState.direction, "down"),
        walkFrame: 0,
      };
      setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
    } else {
      syncSaraFollowerStateForMap(mapDefinition, mapState, currentEnvelope);
    }
    renderMapTiles(mapLayer, mapDefinition, currentEnvelope);
    tickNpcSprites();
    setVisualMapPosition(mapState.tile_x, mapState.tile_y);
    hideCutsceneRingNode();
    persistCurrentMapState(mapState);
    syncMapBgm();
    return true;
  }

  async function runKazusNpc516Sequence(npcRow) {
    const npcKey = npcObjectKey(npcRow);
    const marker = findNpcMarkerByKey(npcKey);
    if (!npcRow || !marker) return false;
    const firstMessages = await loadMergedFixedContentByIndices([516], currentDialoguePartyMembers());
    const secondMessages = await loadMergedFixedContentByIndices([517], currentDialoguePartyMembers());
    const now = performance.now();
    const npcState = npcAnimationStates.get(npcKey) || {
      direction: resolveNpcInitialDirection(npcRow, 0),
      walkFrame: 0,
      nextFrameAt: now + NPC_FRAME_MS,
      nextDirectionAt: now + NPC_DIRECTION_MAX_MS,
    };
    npcAnimationStates.set(npcKey, npcState);
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      await openDialogueMessagesAndWait(firstMessages);
      await animateNpcStep(npcRow, npcState, marker, 3, 27, 500);
      await animateNpcStep(npcRow, npcState, marker, 2, 27, 500);
      await animateNpcStep(npcRow, npcState, marker, 1, 27, 500);
      await waitForDuration(1000);
      await animateNpcStep(npcRow, npcState, marker, 2, 27, 1000);
      await animateNpcStep(npcRow, npcState, marker, 3, 27, 1000);
      await animateNpcStep(npcRow, npcState, marker, 3, 28, 1000);
      npcState.direction = normalizeNpcDirection(npcRow?.direction, "right");
      npcState.walkFrame = 0;
      const spriteNode = marker.querySelector(".map-npc-sprite");
      if (spriteNode) updateNpcSpriteFrame(spriteNode, npcState.direction, npcState.walkFrame);
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      await openDialogueMessagesAndWait(secondMessages);
      mapStatus.textContent = `${npcRow.name || "NPC"} と話しました。`;
      return true;
    } finally {
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      mapTransitionLocked = false;
    }
  }

  async function runKazusCidJoinSequence() {
    const cidRow = (mapDefinition?.objects || []).find((row) => (
      row?.type === "npc" && npcObjectKey(row) === KAZUS_CID_JOIN_KEY
    ));
    const marker = findNpcMarkerByKey(KAZUS_CID_JOIN_KEY);
    if (!cidRow || !marker || !mapState) return false;
    const messages = await loadMergedFixedContentByIndices([16], currentDialoguePartyMembers());
    const now = performance.now();
    const npcState = npcAnimationStates.get(KAZUS_CID_JOIN_KEY) || {
      direction: resolveNpcInitialDirection(cidRow, 0),
      walkFrame: 0,
      nextFrameAt: now + NPC_FRAME_MS,
      nextDirectionAt: now + NPC_DIRECTION_MAX_MS,
    };
    npcAnimationStates.set(KAZUS_CID_JOIN_KEY, npcState);
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      for (const step of KAZUS_CID_JOIN_PATH) {
        await animateNpcStep(cidRow, npcState, marker, step.x, step.y, 500);
      }
      npcState.direction = KAZUS_CID_FOLLOWER_START.direction;
      npcState.walkFrame = 0;
      cidRow.direction = KAZUS_CID_FOLLOWER_START.direction;
      const spriteNode = marker.querySelector(".map-npc-sprite");
      if (spriteNode) updateNpcSpriteFrame(spriteNode, npcState.direction, npcState.walkFrame);
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      await openDialogueMessagesAndWait(messages);
      if (!persistNamedEventFlag(KAZUS_CID_FOLLOWER_EVENT_FLAG)) {
        return false;
      }
      saraFollowerState = {
        current_map_id: String(mapDefinition?.id || KAZUS_MAP_ID),
        tile_x: KAZUS_CID_FOLLOWER_START.x,
        tile_y: KAZUS_CID_FOLLOWER_START.y,
        direction: KAZUS_CID_FOLLOWER_START.direction,
        walkFrame: 0,
      };
      setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      mapStatus.textContent = "シドじいさんが　ついてきた。";
      return true;
    } finally {
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      mapTransitionLocked = false;
    }
  }

  async function runKazusBlacksmithTakaSequence(npcRow) {
    const npcKey = npcObjectKey(npcRow);
    const marker = findNpcMarkerByKey(npcKey);
    if (!npcRow || !marker || !mapState) return false;
    const openingMessages = await loadMergedFixedContentByIndices([535], currentDialoguePartyMembers());
    const completionMessages = await loadMergedFixedContentByIndices([536], currentDialoguePartyMembers());
    const now = performance.now();
    const npcState = npcAnimationStates.get(npcKey) || {
      direction: resolveNpcInitialDirection(npcRow, 0),
      walkFrame: 0,
      nextFrameAt: now + NPC_FRAME_MS,
      nextDirectionAt: now + NPC_DIRECTION_MAX_MS,
    };
    npcAnimationStates.set(npcKey, npcState);
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      await openDialogueMessagesAndWait(openingMessages);
      for (const step of KAZUS_BLACKSMITH_TAKA_OUTBOUND_PATH) {
        await animateNpcStep(npcRow, npcState, marker, step.x, step.y, 500);
      }
      marker.style.display = "none";
      await waitForDuration(3000);
      marker.style.display = "block";
      setNpcMarkerTransform(marker, npcRow);
      for (const step of KAZUS_BLACKSMITH_TAKA_RETURN_PATH) {
        await animateNpcStep(npcRow, npcState, marker, step.x, step.y, 500);
      }
      npcState.direction = "down";
      npcState.walkFrame = 0;
      npcRow.direction = "down";
      const spriteNode = marker.querySelector(".map-npc-sprite");
      if (spriteNode) updateNpcSpriteFrame(spriteNode, npcState.direction, npcState.walkFrame);
      if (!persistNamedEventFlag(KAZUS_BLACKSMITH_MITHRIL_RAM_EVENT_FLAG)) {
        return false;
      }
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      redraw();
      await openDialogueMessagesAndWait(completionMessages);
      mapStatus.textContent = `${npcRow.name || "NPC"} と話しました。`;
      return true;
    } finally {
      marker.style.display = "block";
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      mapTransitionLocked = false;
    }
  }

  async function runFloatingContinentBigRockCrashSequence() {
    if (!mapDefinition || !mapState) return false;
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      await waitForDuration(MAP_MOVE_ANIMATION_MS + 80);
      suppressFloatingContinentAirship = true;
      redraw();
      triggerFlash();
      await playAirshipCrashAnimation(mapLayer, mapDefinition, mapState.tile_x, mapState.tile_y);
      const crashedMapState = {
        ...mapState,
        airship_riding: false,
      };
      delete crashedMapState.airship_tile_x;
      delete crashedMapState.airship_tile_y;
      mapState = crashedMapState;
      const nextEnvelope = buildEnvelopeWithMapState(
        store,
        crashedMapState,
        mapDefinition,
        { clearAirshipState: true },
      );
      ensureMutableSaveEnvelope(nextEnvelope);
      writeSavedEventFlag(nextEnvelope, AIRSHIP_DESTROYED_EVENT_FLAG, true);
      if (!persistMapEventEnvelope(nextEnvelope)) {
        return false;
      }
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      redraw();
      mapStatus.textContent = "ひくうていが　たいはした！";
      return true;
    } finally {
      suppressFloatingContinentAirship = false;
      stopAirshipCrashAnimation(mapLayer);
      mapTransitionLocked = false;
    }
  }

  async function runSealedCaveSaraSequence(npcRow) {
    const npcKey = npcObjectKey(npcRow);
    const marker = findNpcMarkerByKey(npcKey);
    if (!npcRow || !marker || !mapState) return false;
    const openingMessages = await loadMergedFixedContentByIndices([550], currentDialoguePartyMembers());
    const followupMessages = await loadMergedFixedContentByIndices([551], currentDialoguePartyMembers());
    const now = performance.now();
    const npcState = npcAnimationStates.get(npcKey) || {
      direction: resolveNpcInitialDirection(npcRow, 0),
      walkFrame: 0,
      nextFrameAt: now + NPC_FRAME_MS,
      nextDirectionAt: now + NPC_DIRECTION_MAX_MS,
    };
    npcAnimationStates.set(npcKey, npcState);
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      await openDialogueMessagesAndWait(openingMessages);
      for (const target of SEALED_CAVE_B2_2_SARA_PATH) {
        const previousNpcPosition = {
          x: Number(npcRow.x || 0),
          y: Number(npcRow.y || 0),
        };
        await animateNpcStep(npcRow, npcState, marker, target.x, target.y, 500);
        await animatePlayerStepTo(previousNpcPosition.x, previousNpcPosition.y, 500);
      }
      saraFollowerState = {
        current_map_id: String(mapDefinition?.id || SEALED_CAVE_B2_2_MAP_ID),
        tile_x: Number(npcRow.x || 0),
        tile_y: Number(npcRow.y || 0),
        direction: normalizeNpcDirection(npcRow?.direction, "right"),
        walkFrame: 0,
      };
      setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
      const persistedMapState = persistCurrentMapState(mapState);
      const persistedEventFlag = persistNamedEventFlag(SEALED_CAVE_B2_2_SARA_EVENT_FLAG);
      if (!persistedMapState || !persistedEventFlag) return false;
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      redraw();
      await openDialogueMessagesAndWait(followupMessages);
      mapStatus.textContent = `${npcRow.name || "NPC"} と話しました。`;
      return true;
    } finally {
      marker.style.transitionDuration = `${MAP_MOVE_ANIMATION_MS}ms`;
      mapTransitionLocked = false;
    }
  }

  async function runCanaanCidFarewellSequence() {
    if (!mapState || !saraFollowerState || !isCidFollowerActive(store.getState().saveEnvelope)) {
      return false;
    }
    const messages = await loadMergedFixedContentByIndices([17], currentDialoguePartyMembers());
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      const initialPath = buildAxisAlignedPath(
        {
          x: Number(saraFollowerState.tile_x || 0),
          y: Number(saraFollowerState.tile_y || 0),
        },
        CANAAN_CID_INITIAL_DESTINATION,
        { horizontalFirst: false },
      );
      for (const step of initialPath) {
        await animateSaraFollowerStepTo(step.x, step.y, 1000);
      }
      await openDialogueMessagesAndWait(messages);
      const crossroadPath = buildAxisAlignedPath(
        {
          x: Number(saraFollowerState.tile_x || 0),
          y: Number(saraFollowerState.tile_y || 0),
        },
        CANAAN_CID_CROSSROAD_DESTINATION,
        { horizontalFirst: false },
      );
      for (const step of crossroadPath) {
        await animateSaraFollowerStepTo(step.x, step.y, 1000);
      }
      saraFollowerState = {
        ...saraFollowerState,
        direction: "left",
        walkFrame: 0,
      };
      redraw();
      const northPath = buildAxisAlignedPath(
        {
          x: Number(saraFollowerState.tile_x || 0),
          y: Number(saraFollowerState.tile_y || 0),
        },
        CANAAN_CID_NORTH_DESTINATION,
        { horizontalFirst: false },
      );
      for (const step of northPath) {
        await animateSaraFollowerStepTo(step.x, step.y, 1000);
      }
      saraFollowerState = {
        ...saraFollowerState,
        direction: "down",
        walkFrame: 0,
      };
      redraw();
      await waitForDuration(1000);
      await animateSaraFollowerStepToWithFacing(
        CANAAN_CID_EXIT_LANE_DESTINATION.x,
        CANAAN_CID_EXIT_LANE_DESTINATION.y,
        1000,
        "left",
      );
      const exitPath = buildAxisAlignedPath(
        {
          x: Number(saraFollowerState.tile_x || 0),
          y: Number(saraFollowerState.tile_y || 0),
        },
        CANAAN_CID_EXIT_FINAL_DESTINATION,
        { horizontalFirst: false },
      );
      for (const step of exitPath) {
        await animateSaraFollowerStepTo(step.x, step.y, 1000);
      }
      if (!persistNamedEventFlag(CANAAN_CID_FAREWELL_EVENT_FLAG)) {
        return false;
      }
      stopSaraFollowerMoveAnimation();
      visualSaraFollowerPosition = null;
      saraFollowerState = null;
      hideSaraFollowerNode();
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      redraw();
      mapStatus.textContent = "シドじいさんは　カナーンに　のこった。";
      return true;
    } finally {
      mapTransitionLocked = false;
    }
  }

  async function maybeFollowWithSealedCaveSara(previousPlayerState) {
    if (!saraFollowerState || !previousPlayerState || !shouldRenderSaraFollower(store.getState().saveEnvelope)) {
      return false;
    }
    const targetX = Number(previousPlayerState.tile_x);
    const targetY = Number(previousPlayerState.tile_y);
    if (
      Number(saraFollowerState.tile_x || 0) === targetX
      && Number(saraFollowerState.tile_y || 0) === targetY
    ) {
      return false;
    }
    const marker = ensureSaraFollowerNode();
    if (!marker) return false;
    if (!canOccupyTile(mapDefinition, targetX, targetY, store.getState().saveEnvelope)) {
      return false;
    }
    const followerRow = {
      x: Number(saraFollowerState.tile_x || 0),
      y: Number(saraFollowerState.tile_y || 0),
      direction: saraFollowerState.direction,
    };
    const followerState = {
      direction: saraFollowerState.direction,
      walkFrame: saraFollowerState.walkFrame,
    };
    setSaraFollowerVisualPosition(followerRow.x, followerRow.y);
    const deltaX = targetX - followerRow.x;
    const deltaY = targetY - followerRow.y;
    if (deltaX > 0) followerState.direction = "right";
    else if (deltaX < 0) followerState.direction = "left";
    else if (deltaY > 0) followerState.direction = "down";
    else if (deltaY < 0) followerState.direction = "up";
    followerState.walkFrame = followerState.walkFrame === 0 ? 1 : 0;
    saraFollowerState = {
      ...saraFollowerState,
      direction: followerState.direction,
      walkFrame: followerState.walkFrame,
    };
    redraw();
    followerRow.x = targetX;
    followerRow.y = targetY;
    animateSaraFollowerVisualPosition({
      x: saraFollowerState.tile_x,
      y: saraFollowerState.tile_y,
    }, {
      x: targetX,
      y: targetY,
    }, MAP_MOVE_ANIMATION_MS);
    await waitForDuration(MAP_MOVE_ANIMATION_MS);
    saraFollowerState = {
      current_map_id: String(mapDefinition?.id || ""),
      tile_x: Number(followerRow.x || 0),
      tile_y: Number(followerRow.y || 0),
      direction: followerState.direction,
      walkFrame: followerState.walkFrame,
    };
    setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
    return true;
  }

  async function maybeOpenSaraFollowerDialogue() {
    if (!saraFollowerState || !shouldRenderSaraFollower(store.getState().saveEnvelope) || mapTransitionLocked) {
      return false;
    }
    const saveEnvelope = store.getState().saveEnvelope;
    const followerType = activeFollowerType(saveEnvelope);
    const dialogueIndex = followerType === "cid"
      ? resolveCidFollowerDialogueIndex(
        saraFollowerDialogueCount,
        Math.random(),
        isSavedEventFlagEnabled(saveEnvelope, KAZUS_BLACKSMITH_MITHRIL_RAM_EVENT_FLAG),
      )
      : resolveSaraFollowerDialogueIndex(saraFollowerDialogueCount, Math.random());
    const messages = await loadMergedFixedContentByIndices([dialogueIndex], currentDialoguePartyMembers());
    const visibleMessages = messages.filter(Boolean);
    if (!visibleMessages.length) {
      return false;
    }
    saraFollowerDialogueCount += 1;
    if (visibleMessages.length === 1) {
      openEventOverlay(visibleMessages[0]);
    } else {
      openEventOverlaySequence(visibleMessages);
    }
    mapStatus.textContent = followerType === "cid"
      ? "シドじいさんが はなしかけてきた。"
      : "サラひめが はなしかけてきた。";
    return true;
  }

  async function runSealedCaveB3DjinnSequence(_eventRow) {
    if (!mapState) return false;
    const openingMessages = await loadMergedFixedContentByIndices([11], currentDialoguePartyMembers());
    const preBattleMessages = await loadMergedFixedContentByIndices([12], currentDialoguePartyMembers());
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      for (const target of SEALED_CAVE_B3_DJINN_PLAYER_PATH) {
        await animatePlayerStepTo(target.x, target.y, 500);
      }
      persistCurrentMapState(mapState);
      await openDialogueMessagesAndWait(openingMessages);
      if (saraFollowerState) {
        const saraPath = buildAxisAlignedPath(
          {
            x: Number(saraFollowerState.tile_x || 0),
            y: Number(saraFollowerState.tile_y || 0),
          },
          SEALED_CAVE_B3_DJINN_SARA_DESTINATION,
        );
        for (const target of saraPath) {
          await animateSaraFollowerStepTo(target.x, target.y, 500);
        }
      } else {
        saraFollowerState = {
          current_map_id: String(mapDefinition?.id || SEALED_CAVE_B3_MAP_ID),
          tile_x: SEALED_CAVE_B3_DJINN_SARA_DESTINATION.x,
          tile_y: SEALED_CAVE_B3_DJINN_SARA_DESTINATION.y,
          direction: "up",
          walkFrame: 0,
        };
        setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
        redraw();
      }
      triggerFlash();
      await openDialogueMessagesAndWait(preBattleMessages);
      navigateToEncounter({
        enemyNames: ["Djinn"],
        isBoss: true,
        postVictoryEventFlags: [SEALED_CAVE_B3_DJINN_EVENT_FLAG],
        postVictoryCutsceneId: SEALED_CAVE_B3_DJINN_CUTSCENE_ID,
      });
      return true;
    } finally {
      mapTransitionLocked = false;
    }
  }

  async function runPostBattleCutscene(cutsceneId) {
    if (cutsceneId !== SEALED_CAVE_B3_DJINN_CUTSCENE_ID) return false;
    const victoryMessages = await loadMergedFixedContentByIndices([13], currentDialoguePartyMembers());
    const endingMessages = await loadMergedFixedContentByIndices([14], currentDialoguePartyMembers());
    const castleMessages = await loadMergedFixedContentByIndices([15], currentDialoguePartyMembers());
    const farewellMessages = await loadMergedFixedContentByIndices([6], currentDialoguePartyMembers());
    holdRepeater.stop();
    mapTransitionLocked = true;
    try {
      saraFollowerState = {
        current_map_id: String(mapDefinition?.id || SEALED_CAVE_B3_MAP_ID),
        tile_x: SEALED_CAVE_B3_DJINN_SARA_DESTINATION.x,
        tile_y: SEALED_CAVE_B3_DJINN_SARA_DESTINATION.y,
        direction: "up",
        walkFrame: 0,
      };
      setSaraFollowerVisualPosition(saraFollowerState.tile_x, saraFollowerState.tile_y);
      redraw();
      await openDialogueMessagesAndWait(victoryMessages);
      triggerFlash();
      await openDialogueMessagesAndWait(endingMessages);
      await switchMapForCutscene(
        CASTLE_SASUNE_MAINKEEP_B1F_MAP_ID,
        CASTLE_SASUNE_MAINKEEP_POST_DJINN_ENTRY.player,
        { saraState: CASTLE_SASUNE_MAINKEEP_POST_DJINN_ENTRY.sara },
      );
      mapStatus.textContent = "サスーンじょうの いずみに たどりついた。";
      await animateCutsceneRingThrow(
        CASTLE_SASUNE_MAINKEEP_RING_THROW.start,
        CASTLE_SASUNE_MAINKEEP_RING_THROW.end,
        900,
      );
      hideCutsceneRingNode();
      await openDialogueMessagesAndWait(castleMessages);
      forceSaraFollowerVisible = true;
      await animatePlayerStepToWithFacing(5, 6, 500, "left");
      await animatePlayerStepToWithFacing(6, 6, 500, "left");
      await animatePlayerStepToWithFacing(7, 6, 500, "left");
      await animateSaraFollowerStepToWithFacing(6, 6, 500, "right");
      await openDialogueMessagesAndWait(farewellMessages);
      await animatePlayerStepTo(8, 6, 500);
      if (!persistNamedEventFlag(SEALED_CAVE_SARA_LEAVE_EVENT_FLAG)) {
        forceSaraFollowerVisible = false;
        return false;
      }
      mapTransitionLocked = false;
      // Re-enter 4F after the Sara departure flag is saved so the restored NPC set
      // is chosen during the initial render instead of after the first interaction.
      await applyMapTransition(
        CASTLE_SASUNE_MAINKEEP_4F_MAP_ID,
        CASTLE_SASUNE_MAINKEEP_4F_POST_DJINN_SPAWN,
      );
      mapTransitionLocked = true;
      forceSaraFollowerVisible = false;
      saraFollowerState = null;
      hideSaraFollowerNode();
      mapStatus.textContent = "サラひめと わかれ、じょうないへ もどった。";
      return true;
    } finally {
      forceSaraFollowerVisible = false;
      hideCutsceneRingNode();
      mapTransitionLocked = false;
    }
  }

  function clearPendingBgmUnlock() {
    if (typeof cancelPendingBgmUnlock === "function") {
      cancelPendingBgmUnlock();
      cancelPendingBgmUnlock = null;
    }
  }

  function resolveActiveMapBgmUrl() {
    return resolveMapBgmUrl(mapDefinition, store.getState());
  }

  function ensureMapBgmAudio(sourceUrl) {
    const nextSourceUrl = String(sourceUrl || "");
    if (!nextSourceUrl || typeof Audio !== "function") return null;
    try {
      if (!mapBgmAudio) {
        mapBgmAudio = configureLoopingMapBgm(new Audio(), nextSourceUrl);
        currentMapBgmUrl = nextSourceUrl;
        return mapBgmAudio;
      }
      if (currentMapBgmUrl !== nextSourceUrl) {
        mapBgmAudio.pause();
        mapBgmAudio.currentTime = 0;
        configureLoopingMapBgm(mapBgmAudio, nextSourceUrl);
        currentMapBgmUrl = nextSourceUrl;
      }
      return mapBgmAudio;
    } catch (_error) {
      return null;
    }
  }

  function stopMapBgm() {
    clearPendingBgmUnlock();
    if (!mapBgmAudio) return;
    mapBgmAudio.pause();
    mapBgmAudio.currentTime = 0;
    if (currentMapBgmUrl) {
      mapBgmAudio.removeAttribute?.("src");
      mapBgmAudio.src = "";
      mapBgmAudio.load?.();
      currentMapBgmUrl = "";
    }
  }

  function resumeMapBgmFromGesture() {
    clearPendingBgmUnlock();
    syncMapBgm();
  }

  function scheduleBgmUnlockRetry() {
    if (cancelPendingBgmUnlock || typeof window === "undefined") return;
    const retryPlayback = () => {
      resumeMapBgmFromGesture();
    };
    window.addEventListener("pointerdown", retryPlayback, { capture: true });
    window.addEventListener("touchstart", retryPlayback, { capture: true });
    window.addEventListener("click", retryPlayback, { capture: true });
    window.addEventListener("keydown", retryPlayback, { capture: true });
    cancelPendingBgmUnlock = () => {
      window.removeEventListener("pointerdown", retryPlayback, { capture: true });
      window.removeEventListener("touchstart", retryPlayback, { capture: true });
      window.removeEventListener("click", retryPlayback, { capture: true });
      window.removeEventListener("keydown", retryPlayback, { capture: true });
    };
  }

  function syncMapBgm() {
    const sourceUrl = resolveActiveMapBgmUrl();
    if (!sourceUrl) {
      stopMapBgm();
      return;
    }
    const audio = ensureMapBgmAudio(sourceUrl);
    if (!audio || !audio.paused) return;
    configureAmbientAudioSession();
    const playResult = playManagedBgm(audio);
    if (playResult && typeof playResult.catch === "function") {
      playResult.catch(() => {
        if (resolveActiveMapBgmUrl()) {
          scheduleBgmUnlockRetry();
        }
      });
    }
  }

  function isEventOverlayOpen() {
    return mapEventOverlay.classList.contains("open");
  }

  function closeEventOverlay() {
    mapEventOverlay.classList.remove("open");
    mapEventOverlay.setAttribute("aria-hidden", "true");
    const closeAction = eventOverlayCloseAction;
    eventOverlayCloseAction = null;
    if (typeof closeAction === "function") {
      closeAction();
    }
  }

  function openEventOverlay(message, options = {}) {
    mapEventText.textContent = String(message || "");
    eventOverlayCloseAction = typeof options.onClose === "function" ? options.onClose : null;
    mapEventOverlay.classList.add("open");
    mapEventOverlay.setAttribute("aria-hidden", "false");
  }

  function openEventOverlaySequence(messages, options = {}) {
    const rows = Array.isArray(messages)
      ? messages.map((message) => String(message || "")).filter((message) => Boolean(message))
      : [];
    if (!rows.length) return;
    let index = 0;
    const openNext = () => {
      const isLast = index >= rows.length - 1;
      openEventOverlay(rows[index], {
        onClose: () => {
          if (isLast) {
            if (typeof options.onComplete === "function") {
              options.onComplete();
            }
            return;
          }
          index += 1;
          openNext();
        },
      });
    };
    openNext();
  }

  async function openTitleStoryInterlude(options = {}) {
    const lines = ALTER_CAVE_CRYSTAL_OPENING_STORY_LINES.slice();
    if (!lines.length) {
      if (typeof options.onComplete === "function") {
        options.onComplete();
      }
      return;
    }
    openEventOverlaySequence(lines, options);
  }

  async function openPostBattleDialogueSequence(indices, options = {}) {
    const rawIndices = Array.isArray(indices)
      ? indices.map((index) => Number(index)).filter((index) => Number.isFinite(index))
      : [];
    if (!rawIndices.length) {
      if (options.showOpeningStory) {
        await openTitleStoryInterlude(options);
        return;
      }
      if (typeof options.onComplete === "function") {
        options.onComplete();
      }
      return;
    }
    if (options.showOpeningStory && rawIndices.length >= 2) {
      const firstMessages = await loadMergedFixedContentByIndices([rawIndices[0]], currentDialoguePartyMembers());
      const trailingMessages = await loadMergedFixedContentByIndices(rawIndices.slice(1), currentDialoguePartyMembers());
      openEventOverlaySequence(firstMessages, {
        onComplete: async () => {
          await openTitleStoryInterlude({
            onComplete: () => {
              openEventOverlaySequence(trailingMessages, {
                onComplete: options.onComplete,
              });
            },
          });
        },
      });
      return;
    }
    openEventOverlaySequence(await loadMergedFixedContentByIndices(rawIndices, currentDialoguePartyMembers()), options);
  }

  function triggerFlash() {
    mapFlash.classList.remove("active");
    void mapFlash.offsetWidth;
    mapFlash.classList.add("active");
  }

  function patchMapMenuState(partialMenuState) {
    const currentState = store.getState();
    const currentEnvelope = currentState.saveEnvelope && typeof currentState.saveEnvelope === "object"
      ? currentState.saveEnvelope
      : {
        version: 1,
        save: {},
        menu_state: {},
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
        saved_at: new Date().toISOString(),
      };
    const nextMenuState = {
      ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
      ...(partialMenuState && typeof partialMenuState === "object" ? partialMenuState : {}),
    };
    const nextEnvelope = {
      ...currentEnvelope,
      menu_state: nextMenuState,
      selected_location_group: currentState.selectedLocationGroup,
      selected_location: currentState.selectedLocation,
      saved_at: new Date().toISOString(),
    };
    store.updateMenuState(nextMenuState);
    store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" });
  }

  function persistCurrentMapState(nextMapState) {
    if (!mapDefinition) return false;
    const nextEnvelope = buildEnvelopeWithMapState(store, nextMapState, mapDefinition);
    store.updateMenuState(nextEnvelope.menu_state);
    const persisted = store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" });
    if (persisted) {
      triggerAutoSaveFromEnvelope(nextEnvelope);
    }
    return persisted;
  }

  function stopMoveAnimation() {
    if (moveAnimationFrameId !== null) {
      cancelAnimationFrame(moveAnimationFrameId);
      moveAnimationFrameId = null;
    }
    moveAnimation = null;
  }

  function redraw() {
    if (!mapDefinition || !mapState) return;
    const viewportTransform = updateViewportTransform(
      mapViewport,
      mapLayer,
      mapDefinition,
      mapState,
      visualMapPosition,
    );
    updateFloatingContinentAirship(
      mapLayer,
      mapDefinition,
      mapState,
      store.getState().saveEnvelope,
      visualMapPosition,
      { suppressAirship: suppressFloatingContinentAirship },
    );
    updateMapPlayerPosition(mapPlayer, mapDefinition, viewportTransform);
    updateMapPlayerVisibility(mapPlayer, mapDefinition, mapState, store.getState().saveEnvelope);
    updateMapPlayerSpriteImage(mapPlayer, mapDefinition, mapState, store.getState());
    updateMapPlayerSpriteForState(mapPlayer, playerDirection, playerWalkFrame, mapDefinition, mapState, store.getState().saveEnvelope);
    updateSaraFollowerNode();
    updateMeta(mapMeta, mapDefinition, mapState);
  }

  function setVisualMapPosition(tileX, tileY) {
    stopMoveAnimation();
    visualMapPosition = {
      x: asNumber(tileX, 0),
      y: asNumber(tileY, 0),
    };
    redraw();
  }

  function animateVisualMapPosition(previousMapState, nextMapState) {
    const now = performance.now();
    const fromPosition = visualMapPosition
      ? { ...visualMapPosition }
      : resolveMapVisualPosition(null, {
        x: previousMapState?.tile_x,
        y: previousMapState?.tile_y,
      });
    const toPosition = resolveMapVisualPosition(null, {
      x: nextMapState?.tile_x,
      y: nextMapState?.tile_y,
    });
    stopMoveAnimation();
    moveAnimation = {
      fromPosition,
      toPosition,
      startedAt: now,
      durationMs: MAP_MOVE_ANIMATION_MS,
    };
    const tick = (frameNow) => {
      if (!moveAnimation) return;
      const progress = (frameNow - moveAnimation.startedAt) / moveAnimation.durationMs;
      visualMapPosition = interpolateMapPosition(
        moveAnimation.fromPosition,
        moveAnimation.toPosition,
        progress,
      );
      redraw();
      if (progress >= 1) {
        visualMapPosition = { ...moveAnimation.toPosition };
        moveAnimation = null;
        moveAnimationFrameId = null;
        redraw();
        return;
      }
      moveAnimationFrameId = requestAnimationFrame(tick);
    };
    moveAnimationFrameId = requestAnimationFrame(tick);
  }

  function tickNpcSprites(now = performance.now()) {
    const seenKeys = new Set();
    mapLayer.querySelectorAll(".map-npc-sprite").forEach((node) => {
      const key = String(node.dataset.npcKey || "");
      if (!key) return;
      seenKeys.add(key);
      const npcRow = (mapDefinition?.objects || []).find((row) => (
        row?.type === "npc"
        && npcObjectKey(row) === key
      ));
      const movement = normalizeNpcMovement(npcRow?.movement);
      let npcState = npcAnimationStates.get(key);
      if (!npcState) {
        const direction = resolveNpcInitialDirection(npcRow, Math.random());
        npcState = {
          direction,
          walkFrame: 0,
          nextFrameAt: now + NPC_FRAME_MS,
          nextDirectionAt: now + resolveNpcNextDirectionDelay(Math.random()),
        };
        npcAnimationStates.set(key, npcState);
      }
      if (movement === NPC_MOVEMENT_RANDOM && now >= npcState.nextDirectionAt) {
        npcState.direction = chooseNextNpcDirection(npcState.direction, Math.random());
        const delta = directionDelta(npcState.direction);
        const nextX = Number(npcRow?.x || 0) + Number(delta?.x || 0);
        const nextY = Number(npcRow?.y || 0) + Number(delta?.y || 0);
        if (npcRow && canNpcTraverseBetweenTiles(
          mapDefinition,
          npcRow,
          mapState,
          Number(npcRow?.x || 0),
          Number(npcRow?.y || 0),
          nextX,
          nextY,
        )) {
          npcRow.x = nextX;
          npcRow.y = nextY;
          const marker = node.closest(".map-object-npc");
          const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
          marker.style.transform = npcTileTransform(npcRow, renderPadding);
        }
        npcState.nextDirectionAt = now + resolveNpcNextDirectionDelay(Math.random());
      } else if (movement !== NPC_MOVEMENT_RANDOM) {
        const configuredDirection = normalizeNpcDirection(npcRow?.direction, "");
        if (configuredDirection) npcState.direction = configuredDirection;
      }
      if (now >= npcState.nextFrameAt) {
        npcState.walkFrame = npcState.walkFrame === 0 ? 1 : 0;
        npcState.nextFrameAt = now + NPC_FRAME_MS;
      }
      updateNpcSpriteFrame(node, npcState.direction, npcState.walkFrame);
    });
    Array.from(npcAnimationStates.keys()).forEach((key) => {
      if (!seenKeys.has(key)) npcAnimationStates.delete(key);
    });
    tickSaraFollower(now);
  }

  function startNpcAnimation() {
    if (npcAnimationIntervalId !== null) return;
    tickNpcSprites();
    npcAnimationIntervalId = window.setInterval(() => tickNpcSprites(), 250);
  }

  function stopNpcAnimation() {
    if (npcAnimationIntervalId === null) return;
    window.clearInterval(npcAnimationIntervalId);
    npcAnimationIntervalId = null;
  }

  function ensureMutableSaveEnvelope(envelope) {
    if (!envelope.save || typeof envelope.save !== "object") {
      envelope.save = { gil: 0, inventory: {}, party: [] };
    }
    if (!envelope.menu_state || typeof envelope.menu_state !== "object") {
      envelope.menu_state = {
        party: [],
        resources: { cp: 0, cp_max: 255, gil: envelope.save.gil || 0 },
      };
    }
  }

  function persistMapEventEnvelope(nextEnvelope) {
    const currentState = store.getState();
    nextEnvelope.saved_at = new Date().toISOString();
    nextEnvelope.selected_location_group = currentState.selectedLocationGroup;
    nextEnvelope.selected_location = currentState.selectedLocation;
    if (nextEnvelope.menu_state && typeof nextEnvelope.menu_state === "object") {
      store.updateMenuState(nextEnvelope.menu_state);
    }

    if (!store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" })) {
      mapStatus.textContent = "イベント結果の保存に失敗しました。";
      return false;
    }

    persistMenuStateFromEnvelope(nextEnvelope);
    triggerAutoSaveFromEnvelope(nextEnvelope);
    return true;
  }

  function persistNamedEventFlag(flagKey) {
    if (!flagKey) return true;
    return persistNamedEventFlags([flagKey]);
  }

  function persistNamedEventFlags(flagKeys) {
    const names = Array.isArray(flagKeys)
      ? flagKeys.map((flag) => String(flag || "")).filter((flag) => Boolean(flag))
      : [];
    if (!names.length) return true;
    const currentState = store.getState();
    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    ensureMutableSaveEnvelope(nextEnvelope);
    names.forEach((flagKey) => {
      writeSavedEventFlag(nextEnvelope, flagKey, true);
    });
    return persistMapEventEnvelope(nextEnvelope);
  }

  async function triggerStandingEvent(eventRow) {
    if (!eventRow || typeof eventRow !== "object") return false;
    if (String(eventRow.scripted_sequence || "") === SEALED_CAVE_B3_DJINN_CUTSCENE_ID) {
      return runSealedCaveB3DjinnSequence(eventRow);
    }
    if (String(eventRow.scripted_sequence || "") === KAZUS_CID_JOIN_SEQUENCE_ID) {
      return runKazusCidJoinSequence();
    }
    if (String(eventRow.scripted_sequence || "") === CANAAN_CID_FAREWELL_SEQUENCE_ID) {
      return runCanaanCidFarewellSequence();
    }
    const enemyNames = eventEnemyNames(eventRow);
    if (enemyNames.length) {
      const startEncounter = () => {
        mapStatus.textContent = `${enemyNames.join(" / ")} が現れた！`;
        navigateToEncounter({
          enemyNames,
          postVictoryOverlayIndices: eventPostVictoryDialogueIndices(eventRow),
          postVictoryEventFlags: eventRow.set_event_flag ? [String(eventRow.set_event_flag)] : [],
          postVictoryShowOpeningStory: eventRow.post_victory_show_opening_story === true,
        });
      };
      const messages = await loadMergedFixedContentByIndices(npcDialogueIndices(eventRow), currentDialoguePartyMembers());
      const visibleMessages = messages.filter((message) => Boolean(message));
      if (visibleMessages.length === 1) {
        openEventOverlay(visibleMessages[0], { onClose: startEncounter });
      } else if (visibleMessages.length > 1) {
        openEventOverlaySequence(visibleMessages, { onComplete: startEncounter });
      } else {
        startEncounter();
      }
      return true;
    }
    if (!persistNamedEventFlag(eventRow.set_event_flag)) {
      return true;
    }
    const messages = await loadMergedFixedContentByIndices(npcDialogueIndices(eventRow), currentDialoguePartyMembers());
    const visibleMessages = messages.filter((message) => Boolean(message));
    if (visibleMessages.length === 1) {
      openEventOverlay(visibleMessages[0]);
    } else if (visibleMessages.length > 1) {
      openEventOverlaySequence(visibleMessages);
    }
    mapStatus.textContent = `${eventRow.name || "イベント"} が発生しました。`;
    return true;
  }

  async function runFullRecoveryEvent(textIndex, statusText) {
    if (!pyodide) {
      const pyodideRuntime = await import("../pyodide_runtime.js");
      pyodide = await pyodideRuntime.getPyodideRuntime();
    }
    const currentState = store.getState();
    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    ensureMutableSaveEnvelope(nextEnvelope);

    const recoveredParty = await buildRecoveredPartySnapshot(
      pyodide,
      nextEnvelope.save,
      currentState.selectedLocationGroup,
      currentState.selectedLocation,
    );
    if (!recoveredParty.length) {
      mapStatus.textContent = "回復イベントの実行に失敗しました。";
      return;
    }

    syncSavePartyRecovery(nextEnvelope.save, recoveredParty);
    syncMenuPartyRecovery(nextEnvelope.menu_state, recoveredParty);
    nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextEnvelope.menu_state);
    if (!persistMapEventEnvelope(nextEnvelope)) return;
    triggerFlash();
    openEventOverlay(await loadMergedFixedContentByIndexWithCharacterName(textIndex, currentDialoguePartyMembers()));
    mapStatus.textContent = statusText;
  }

  async function runAlterCaveRecoveryEvent() {
    await runFullRecoveryEvent(
      ALTER_CAVE_RECOVERY_TEXT_INDEX,
      "不思議な力で HP・MP が回復した。",
    );
  }

  async function runUrElderHouseReviveEvent() {
    const currentState = store.getState();
    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    ensureMutableSaveEnvelope(nextEnvelope);

    const revivedCount = reviveZeroHpPartyMembersToOneHp(nextEnvelope.save, nextEnvelope.menu_state);
    nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextEnvelope.menu_state);
    if (!persistMapEventEnvelope(nextEnvelope)) return;
    triggerFlash();
    openEventOverlay(await loadMergedFixedContentByIndexWithCharacterName(
      UR_ELDER_HOUSE_REVIVE_TEXT_INDEX,
      currentDialoguePartyMembers(),
    ));
    mapStatus.textContent = revivedCount > 0
      ? "不思議な力で倒れた仲間がよみがえった。"
      : "不思議な力があたりを満たしている。";
  }

  async function tryConfirm() {
    if (!mapDefinition || !mapState || mapTransitionLocked || isEventOverlayOpen()) return;
    const currentEnvelope = store.getState().saveEnvelope;
    if (isStandingOnAirship(mapDefinition, mapState, currentEnvelope)) {
      mapState = {
        ...mapState,
        airship_riding: true,
      };
      persistCurrentMapState(mapState);
      redraw();
      mapStatus.textContent = "ひくうていに のりこんだ！";
      return;
    }
    if (isAirshipRiding(mapDefinition, mapState, currentEnvelope)) {
      if (!canOccupyCurrentTravelMode(mapDefinition, mapState, currentEnvelope)) {
        mapStatus.textContent = "ここでは ひくうていを おりられません。";
        return;
      }
      mapState = {
        ...mapState,
        airship_riding: false,
      };
      persistCurrentMapState(mapState);
      redraw();
      mapStatus.textContent = "ひくうていを おりた。";
      return;
    }
    const shopActivation = findShopActivation(mapDefinition, mapState);
    if (shopActivation) {
      sessionStorage.setItem(SHOP_START_CONTEXT_KEY, JSON.stringify({
        return_route: "map",
        map_id: mapDefinition.id,
        map: shopActivation.shopMap,
        type: shopActivation.shopType,
      }));
      patchMapMenuState({ map_return_pending: true });
      mapStatus.textContent = `${shopActivation.shopType} shop を開きます。`;
      navigate("shop");
      return;
    }
    if (
      mapDefinition.id === ALTER_CAVE_RECOVERY_MAP_ID
      && findAdjacentTileWithGid(mapDefinition, mapState, ALTER_CAVE_RECOVERY_GID)
    ) {
      await runAlterCaveRecoveryEvent();
      return;
    }
    if (
      mapDefinition.id === UR_ELDER_HOUSE_1_MAP_ID
      && isAdjacentToTileCoordinate(mapState, UR_ELDER_HOUSE_FULL_RECOVERY_SPRING)
    ) {
      await runFullRecoveryEvent(
        UR_ELDER_HOUSE_FULL_RECOVERY_TEXT_INDEX,
        "不思議な力で HP・MP が回復した。",
      );
      return;
    }
    if (
      mapDefinition.id === UR_ELDER_HOUSE_1_MAP_ID
      && isFacingTileCoordinate(mapState, UR_ELDER_HOUSE_REVIVE_SPRING)
    ) {
      await runUrElderHouseReviveEvent();
      return;
    }
    if (
      mapDefinition.id === KAZUS_SHRINE_MAP_ID
      && isFacingTileCoordinate(mapState, KAZUS_SHRINE_REVIVE_SPRING)
    ) {
      await runUrElderHouseReviveEvent();
      return;
    }
    if (
      mapDefinition.id === AIRSHIP_OF_CID_MAP_ID
      && isFacingTileCoordinate(mapState, AIRSHIP_OF_CID_HELM_TILE)
    ) {
      if (!isSavedEventFlagEnabled(store.getState().saveEnvelope, AIRSHIP_OBTAINED_EVENT_FLAG)) {
        if (!persistNamedEventFlag(AIRSHIP_OBTAINED_EVENT_FLAG)) return;
      }
      const moved = await applyMapTransition(FLOATING_CONTINENT_MAP_ID, AIRSHIP_FLOATING_CONTINENT_TILE);
      if (moved) {
        mapStatus.textContent = "ひくうていを てにいれた！";
      } else {
        mapStatus.textContent = "ひくうていの離陸に失敗しました。";
      }
      return;
    }
    const adjacentNpc = findAdjacentNpc(mapDefinition, mapState, store.getState().saveEnvelope);
    if (adjacentNpc) {
      if (
        mapDefinition.id === KAZUS_MAP_ID
        && npcObjectKey(adjacentNpc) === KAZUS_NPC_516_KEY
      ) {
        await runKazusNpc516Sequence(adjacentNpc);
        return;
      }
      if (
        mapDefinition.id === SEALED_CAVE_B2_2_MAP_ID
        && npcObjectKey(adjacentNpc) === SEALED_CAVE_B2_2_SARA_KEY
        && !isSavedEventFlagEnabled(store.getState().saveEnvelope, SEALED_CAVE_B2_2_SARA_EVENT_FLAG)
      ) {
        await runSealedCaveSaraSequence(adjacentNpc);
        return;
      }
      if (
        mapDefinition.id === KAZUS_BLACKSMITH_MAP_ID
        && npcObjectKey(adjacentNpc) === KAZUS_BLACKSMITH_TAKA_KEY
        && isCidFollowerActive(store.getState().saveEnvelope)
        && !isSavedEventFlagEnabled(store.getState().saveEnvelope, KAZUS_BLACKSMITH_MITHRIL_RAM_EVENT_FLAG)
      ) {
        await runKazusBlacksmithTakaSequence(adjacentNpc);
        return;
      }
      const dialogueIndices = resolveNpcDialogueIndicesForInteraction(
        mapDefinition,
        adjacentNpc,
        store.getState().saveEnvelope,
      );
      const messages = await loadMergedFixedContentByIndices(dialogueIndices, currentDialoguePartyMembers());
      const visibleMessages = messages.filter((message) => Boolean(message));
      if (visibleMessages.length > 0) {
        if (visibleMessages.length === 1) {
          openEventOverlay(visibleMessages[0]);
        } else {
          openEventOverlaySequence(visibleMessages);
        }
        const eventFlagsToPersist = [
          adjacentNpc.set_event_flag,
          (
            mapDefinition.id === CASTLE_SASUNE_MAINKEEP_4F_MAP_ID
            && dialogueIndices.includes(545)
          ) ? CANOE_OBTAINED_EVENT_FLAG : "",
        ];
        if (persistNamedEventFlags(eventFlagsToPersist)) {
          renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
          tickNpcSprites();
          redraw();
        }
        mapStatus.textContent = `${adjacentNpc.name || "NPC"} と話しました。`;
      } else {
        mapStatus.textContent = "このNPCの会話テキストが見つかりません。";
      }
      return;
    }
    const switchResult = toggleAdjacentSwitch(mapDefinition, mapState);
    if (switchResult.toggled) {
      mapDefinition = switchResult.mapDefinition;
      mapState = switchResult.mapState;
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      persistCurrentMapState(mapState);
      redraw();
      mapStatus.textContent = `${switchResult.switchId} を ${switchResult.enabled ? "ON" : "OFF"} にしました。`;
      return;
    }
    const treasureResult = openAdjacentTreasure(
      mapDefinition,
      mapState,
      store.getState().saveEnvelope,
      spellLevelByName,
    );
    if (treasureResult.opened) {
      mapDefinition = treasureResult.mapDefinition;
      mapState = treasureResult.mapState;
      renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
      tickNpcSprites();
      const currentState = store.getState();
      const nextEnvelope = {
        ...(treasureResult.saveEnvelope || currentState.saveEnvelope || { save: {}, menu_state: {} }),
        menu_state: {
          ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
          map_state: {
            ...mapState,
          },
        },
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
        saved_at: new Date().toISOString(),
      };
      store.updateMenuState(nextEnvelope.menu_state);
      const persisted = store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" });
      if (persisted) {
        triggerAutoSaveFromEnvelope(nextEnvelope);
      }
      redraw();
      mapStatus.textContent = treasureGainStatusText(treasureResult);
      return;
    }
    if (treasureResult.guardedBattle) {
      mapStatus.textContent = `${treasureResult.enemyNames[0]} が宝箱を守っている！`;
      navigateToEncounter({
        enemyNames: treasureResult.enemyNames,
        postVictoryTreasureContext: treasureResult.pendingTreasureContext,
      });
      return;
    }
    if (treasureResult.inventoryError) {
      mapStatus.textContent = `${treasureResult.itemName} の保存先を解決できませんでした。`;
      return;
    }
    mapStatus.textContent = treasureResult.alreadyOpened
      ? "その宝箱はすでに開いています。"
      : "反応するギミックは近くにありません。";
  }

  async function applyMapTransition(targetMapId, targetSpawn = null) {
    if (!targetMapId || mapTransitionLocked) return false;
    mapTransitionLocked = true;
    try {
      const nextMapDefinition = await loadMapDefinition(String(targetMapId));
      const currentEnvelope = store.getState().saveEnvelope;
      const savedOpenedTreasures = readSavedTreasureStates(currentEnvelope, nextMapDefinition.id);
      const storeState = store.getState();
      const resolvedSpawn = resolveTransitionSpawn(nextMapDefinition, targetSpawn);
      const nextSelection = resolveEncounterSelectionForMapState(nextMapDefinition, {
        selected_location_group: storeState.selectedLocationGroup,
        selected_location: storeState.selectedLocation,
      }, {
        tile_x: resolvedSpawn.x,
        tile_y: resolvedSpawn.y,
      }, currentEnvelope);
      mapDefinition = nextMapDefinition;
      mapState = applyResolvedAirshipState(nextMapDefinition, {
        current_map_id: nextMapDefinition.id,
        tile_x: resolvedSpawn.x,
        tile_y: resolvedSpawn.y,
        current_movement_plane: "ground",
        facing_direction: playerDirection,
        steps_since_reset: 0,
        switch_states: {},
        opened_treasures: savedOpenedTreasures,
      }, storeState.menuState, currentEnvelope);
      store.patch({
        selectedLocationGroup: nextSelection.selected_location_group,
        selectedLocation: nextSelection.selected_location,
      });
      if (!canOccupyTile(mapDefinition, mapState.tile_x, mapState.tile_y, currentEnvelope)) {
        mapState = applyResolvedAirshipState(nextMapDefinition, {
          current_map_id: nextMapDefinition.id,
          tile_x: asNumber(nextMapDefinition.spawn?.x, 0),
          tile_y: asNumber(nextMapDefinition.spawn?.y, 0),
          current_movement_plane: "ground",
          facing_direction: playerDirection,
          steps_since_reset: 0,
          switch_states: {},
          opened_treasures: savedOpenedTreasures,
        }, storeState.menuState, currentEnvelope);
      }
      mapDefinition = applySwitchStateToMap(
        { ...mapDefinition, openedTreasures: mapState.opened_treasures },
        mapState.switch_states,
      );
      syncSaraFollowerStateForMap(mapDefinition, mapState, currentEnvelope);
      renderMapTiles(mapLayer, mapDefinition, currentEnvelope);
      tickNpcSprites();
      setVisualMapPosition(mapState.tile_x, mapState.tile_y);
      persistCurrentMapState(mapState);
      syncMapBgm();
      mapStatus.textContent = `${mapDefinition.name} に移動しました。`;
      return true;
    } finally {
      mapTransitionLocked = false;
    }
  }

  function navigateToEncounter(options = {}) {
    if (!mapDefinition || encounterLocked) return;
    encounterLocked = true;
    const storeState = store.getState();
    const encounterSelection = resolveEncounterSelectionForMapState(mapDefinition, {
      selected_location_group: storeState.selectedLocationGroup,
      selected_location: storeState.selectedLocation,
    }, mapState, storeState.saveEnvelope);
    const forcedEnemyNames = Array.isArray(options?.enemyNames)
      ? options.enemyNames.map((name) => String(name || "")).filter((name) => Boolean(name))
      : [];
    const isBossEncounter = options?.isBoss === true
      || forcedEnemyNames.includes(ALTER_CAVE_CRYSTAL_BOSS_NAME);
    const postVictoryOverlayIndices = Array.isArray(options?.postVictoryOverlayIndices)
      ? options.postVictoryOverlayIndices.map((index) => Number(index)).filter((index) => Number.isFinite(index))
      : [];
    const postVictoryEventFlags = Array.isArray(options?.postVictoryEventFlags)
      ? options.postVictoryEventFlags.map((flag) => String(flag || "")).filter((flag) => Boolean(flag))
      : [];
    const postVictoryShowOpeningStory = options?.postVictoryShowOpeningStory === true;
    const postVictoryCutsceneId = String(options?.postVictoryCutsceneId || "");
    const postVictoryTreasureContext = (
      options?.postVictoryTreasureContext && typeof options.postVictoryTreasureContext === "object"
        ? {
          map_id: String(options.postVictoryTreasureContext.map_id || mapDefinition?.id || ""),
          treasure_key: String(options.postVictoryTreasureContext.treasure_key || ""),
        }
        : null
    );
    sessionStorage.setItem(BATTLE_START_SELECTION_KEY, JSON.stringify({
      ...encounterSelection,
      ...(forcedEnemyNames.length ? { enemy_names: forcedEnemyNames } : {}),
      ...(isBossEncounter ? { is_boss: true } : {}),
    }));
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify({
      return_route: "map",
      resume_map: true,
      map_id: mapDefinition.id,
      ...(postVictoryOverlayIndices.length ? { post_victory_overlay_indices: postVictoryOverlayIndices } : {}),
      ...(postVictoryEventFlags.length ? { post_victory_event_flags: postVictoryEventFlags } : {}),
      ...(postVictoryShowOpeningStory ? { post_victory_show_opening_story: true } : {}),
      ...(postVictoryCutsceneId ? { post_victory_cutscene_id: postVictoryCutsceneId } : {}),
      ...(postVictoryTreasureContext?.treasure_key ? { post_victory_treasure_context: postVictoryTreasureContext } : {}),
    }));
    store.patch({
      selectedLocationGroup: encounterSelection.selected_location_group,
      selectedLocation: encounterSelection.selected_location,
    });
    navigate("battle");
  }

  async function tryMove(direction) {
    if (!mapDefinition || !mapState || mapTransitionLocked) return;
    const previousMapState = mapState;
    playerDirection = normalizeMapFacingDirection(direction, playerDirection);
    const currentEnvelope = store.getState().saveEnvelope;
    const delta = directionDelta(playerDirection);
    const attemptedNextX = asNumber(mapState?.tile_x, 0) + asNumber(delta?.x, 0);
    const attemptedNextY = asNumber(mapState?.tile_y, 0) + asNumber(delta?.y, 0);
    const result = isAirshipRiding(mapDefinition, mapState, currentEnvelope)
      ? moveAirshipPosition(mapDefinition, mapState, direction, currentEnvelope)
      : moveMapPosition(mapDefinition, mapState, direction, currentEnvelope);
    mapState = result.nextState;
    if (!result.moved) {
      playerWalkFrame = 0;
      updateMapPlayerSpriteForState(mapPlayer, playerDirection, playerWalkFrame, mapDefinition, mapState, currentEnvelope);
      persistCurrentMapState(mapState);
      mapStatus.textContent = result.reason === "blocked"
        ? (isAirshipRiding(mapDefinition, mapState, currentEnvelope)
          ? "その方向には ひくうていで進めません。"
          : "その方向には進めません。")
        : "移動できません。";
      return;
    }
    playerWalkFrame = playerWalkFrame === 0 ? 1 : 0;
    const movementSelection = resolveEncounterSelectionForMapState(
      mapDefinition,
      {
        selected_location_group: store.getState().selectedLocationGroup,
        selected_location: store.getState().selectedLocation,
      },
      mapState,
      currentEnvelope,
    );
    if (
      movementSelection.selected_location_group
      && movementSelection.selected_location
      && (
        movementSelection.selected_location_group !== store.getState().selectedLocationGroup
        || movementSelection.selected_location !== store.getState().selectedLocation
      )
    ) {
      store.patch({
        selectedLocationGroup: movementSelection.selected_location_group,
        selectedLocation: movementSelection.selected_location,
      });
    }
    persistCurrentMapState(mapState);
    animateVisualMapPosition(previousMapState, mapState);
    if (shouldTriggerFloatingContinentBigRockCrash(
      mapDefinition,
      mapState,
      attemptedNextX,
      attemptedNextY,
      currentEnvelope,
    )) {
      await runFloatingContinentBigRockCrashSequence();
      return;
    }
    if (!isAirshipRiding(mapDefinition, mapState, currentEnvelope)) {
      mapTransitionLocked = true;
      try {
        await maybeFollowWithSealedCaveSara(previousMapState);
      } finally {
        mapTransitionLocked = false;
      }
    }
    if (isAirshipRiding(mapDefinition, mapState, currentEnvelope)) {
      mapStatus.textContent = "ひくうていで移動しました。";
      return;
    }
    const standingObject = findStandingObject(mapDefinition, mapState, store.getState().saveEnvelope);
    if (standingObject?.type === "exit" && standingObject?.target_map) {
      if (!persistNamedEventFlag(standingObject.set_event_flag)) {
        return;
      }
      const moved = await applyMapTransition(
        String(standingObject.target_map),
        standingObject.target_spawn,
      );
      if (!moved) {
        mapStatus.textContent = "出入口の移動に失敗しました。";
      }
      return;
    }
    if (isCastleSasuneTowerEast4FRecoveryTile(mapDefinition, mapState)) {
      await runFullRecoveryEvent(
        CASTLE_SASUNE_TOWER_EAST_4F_RECOVERY_TEXT_INDEX,
        "HP・MP と状態異常が回復した。",
      );
      return;
    }
    if (
      isUrInnItemShopRecoveryTile(mapDefinition, mapState)
      || isKazusInnItemShopRecoveryTile(mapDefinition, mapState)
      || isCastleSasuneMainKeep1FRecoveryTile(mapDefinition, mapState)
    ) {
      await runFullRecoveryEvent(
        UR_INN_ITEMSHOP_RECOVERY_TEXT_INDEX,
        "HP・MP と状態異常が回復した。",
      );
      return;
    }
    const standingEvent = findStandingEventTrigger(
      mapDefinition,
      mapState,
      store.getState().saveEnvelope,
    );
    if (standingEvent) {
      await triggerStandingEvent(standingEvent);
      return;
    }
    const standing = describeStandingObject(mapDefinition, mapState);
    if (shouldTriggerEncounter(
      mapDefinition,
      Math.random(),
      asNumber(mapState?.steps_since_reset, 0),
      mapState,
    )) {
      mapStatus.textContent = "敵が現れた！ 戦闘へ移行します。";
      navigateToEncounter();
      return;
    }
    mapStatus.textContent = standing || "移動しました。";
  }

  const onKeyDown = (event) => {
    resumeMapBgmFromGesture();
    if (isEventOverlayOpen()) {
      if (event.key === "Enter" || event.key === " " || event.key === "Escape") {
        event.preventDefault();
        closeEventOverlay();
      }
      return;
    }
    const keyMap = {
      ArrowUp: "up",
      ArrowDown: "down",
      ArrowLeft: "left",
      ArrowRight: "right",
    };
    const direction = keyMap[event.key];
    if (direction) {
      event.preventDefault();
      void tryMove(direction);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void tryConfirm();
    }
  };

  const onConfirm = () => {
    resumeMapBgmFromGesture();
    if (shouldCloseEventOverlayOnConfirm(isEventOverlayOpen())) {
      closeEventOverlay();
      return;
    }
    void tryConfirm();
  };
  const onCloseEvent = () => {
    resumeMapBgmFromGesture();
    closeEventOverlay();
  };
  const onCancel = () => {
    resumeMapBgmFromGesture();
    if (isEventOverlayOpen()) {
      closeEventOverlay();
      return;
    }
    if (shouldRenderSaraFollower(store.getState().saveEnvelope)) {
      void maybeOpenSaraFollowerDialogue();
      return;
    }
    patchMapMenuState({ map_return_pending: true });
    navigate("menu");
  };
  const onGoLocation = () => {
    resumeMapBgmFromGesture();
    patchMapMenuState({ map_return_pending: false });
    navigate("location");
  };
  const onGoMenu = () => {
    resumeMapBgmFromGesture();
    patchMapMenuState({ map_return_pending: true });
    navigate("menu");
  };
  const onGoBattle = () => {
    resumeMapBgmFromGesture();
    navigate("battle");
  };
  const padHandlers = new Map();

  confirmBtn.addEventListener("click", onConfirm);
  cancelBtn.addEventListener("click", onCancel);
  locationBtn.addEventListener("click", onGoLocation);
  menuBtn.addEventListener("click", onGoMenu);
  battleBtn.addEventListener("click", onGoBattle);
  mapEventCloseBtn.addEventListener("click", onCloseEvent);
  padButtons.forEach((button) => {
    const direction = String(button.dataset.dir || "");
    const onPointerDown = (event) => {
      event.preventDefault();
      resumeMapBgmFromGesture();
      holdRepeater.start(direction);
    };
    const onPointerUp = (event) => {
      event.preventDefault();
      holdRepeater.stop(direction);
    };
    const onPointerLeave = () => {
      holdRepeater.stop(direction);
    };
    padHandlers.set(button, {
      onPointerDown,
      onPointerUp,
      onPointerLeave,
    });
    button.addEventListener("pointerdown", onPointerDown);
    button.addEventListener("pointerup", onPointerUp);
    button.addEventListener("pointercancel", onPointerUp);
    button.addEventListener("pointerleave", onPointerLeave);
  });
  window.addEventListener("keydown", onKeyDown);

  try {
    const appState = store.getState();
    const battleReturnContext = readBattleReturnContext();
    const mapEntryContext = readMapEntryContext();
    const {
      freshLocationEntry,
      resumeFromSavedPosition,
      returningFromBattle,
      requestedMapId,
    } = deriveMapLaunchContext(appState, battleReturnContext, mapEntryContext);
    const postBattleOverlayIndices = returningFromBattle
      && Array.isArray(battleReturnContext?.pending_overlay_indices)
      ? battleReturnContext.pending_overlay_indices
      : [];
    const postBattleEventFlags = returningFromBattle
      && Array.isArray(battleReturnContext?.pending_event_flags)
      ? battleReturnContext.pending_event_flags
      : [];
    const postBattleShowOpeningStory = returningFromBattle
      && battleReturnContext?.pending_opening_story === true;
    const postBattleCutsceneId = returningFromBattle
      ? String(battleReturnContext?.pending_cutscene_id || "")
      : "";
    const postBattleTreasureContext = returningFromBattle
      && battleReturnContext?.pending_treasure_context
      && typeof battleReturnContext.pending_treasure_context === "object"
      ? battleReturnContext.pending_treasure_context
      : null;
    spellLevelByName = await loadSpellLevelByName();
    mapDefinition = await loadMapDefinition(requestedMapId);
    const currentSelection = resolveInitialMapSelection(appState, mapDefinition, {
      returningFromBattle,
      resumeFromSavedPosition,
    });
    if (returningFromBattle || resumeFromSavedPosition) {
      store.patch({
        selectedLocationGroup: currentSelection.selected_location_group,
        selectedLocation: currentSelection.selected_location,
      });
    }
    if (!isMapSelectionCompatible(mapDefinition, currentSelection)) {
      mapStatus.textContent = "現在のLocationではこのマップへ移動できません。";
      mapMeta.innerHTML = "<div>Locationを対応する場所に合わせてから移動してください。</div>";
      return () => {
        confirmBtn.removeEventListener("click", onConfirm);
        cancelBtn.removeEventListener("click", onCancel);
        locationBtn.removeEventListener("click", onGoLocation);
        menuBtn.removeEventListener("click", onGoMenu);
        battleBtn.removeEventListener("click", onGoBattle);
        mapEventCloseBtn.removeEventListener("click", onCloseEvent);
        padButtons.forEach((button) => {
          const handlers = padHandlers.get(button);
          if (!handlers) return;
          button.removeEventListener("pointerdown", handlers.onPointerDown);
          button.removeEventListener("pointerup", handlers.onPointerUp);
          button.removeEventListener("pointercancel", handlers.onPointerUp);
          button.removeEventListener("pointerleave", handlers.onPointerLeave);
        });
        holdRepeater.stop();
        stopNpcAnimation();
        stopAirshipCrashAnimation(mapLayer);
        stopMapBgm();
        window.removeEventListener("keydown", onKeyDown);
      };
    }
    mapState = deriveInitialMapState(appState, mapDefinition, {
      resumeFromSavedPosition,
    });
    const initialEncounterSelection = resolveEncounterSelectionForMapState(
      mapDefinition,
      currentSelection,
      mapState,
      store.getState().saveEnvelope,
    );
    if (
      initialEncounterSelection.selected_location_group
      && initialEncounterSelection.selected_location
      && (
        initialEncounterSelection.selected_location_group !== store.getState().selectedLocationGroup
        || initialEncounterSelection.selected_location !== store.getState().selectedLocation
      )
    ) {
      store.patch({
        selectedLocationGroup: initialEncounterSelection.selected_location_group,
        selectedLocation: initialEncounterSelection.selected_location,
      });
    }
    playerDirection = normalizeMapFacingDirection(mapState?.facing_direction, "down");
    mapDefinition = applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: mapState.opened_treasures },
      mapState.switch_states,
    );
    syncSaraFollowerStateForMap(mapDefinition, mapState, store.getState().saveEnvelope);
    let postBattleTreasureResult = null;
    if (postBattleTreasureContext) {
      postBattleTreasureResult = applyPendingGuardedTreasureReward(
        mapDefinition,
        mapState,
        store.getState().saveEnvelope,
        postBattleTreasureContext,
        spellLevelByName,
      );
      if (postBattleTreasureResult.opened) {
        mapDefinition = postBattleTreasureResult.mapDefinition;
        mapState = postBattleTreasureResult.mapState;
        const currentState = store.getState();
        const nextEnvelope = {
          ...(postBattleTreasureResult.saveEnvelope || currentState.saveEnvelope || { save: {}, menu_state: {} }),
          menu_state: {
            ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
            map_state: {
              ...mapState,
            },
          },
          selected_location_group: currentState.selectedLocationGroup,
          selected_location: currentState.selectedLocation,
          saved_at: new Date().toISOString(),
        };
        store.updateMenuState(nextEnvelope.menu_state);
        const persisted = store.updateSaveEnvelope(nextEnvelope, { reason: "battle_finished" });
        if (persisted) {
          triggerAutoSaveFromEnvelope(nextEnvelope);
        }
      }
    }
    if (freshLocationEntry) {
      sessionStorage.removeItem(MAP_ENTRY_CONTEXT_KEY);
      patchMapMenuState({ map_return_pending: false });
    }
    if (
      freshLocationEntry
      && mapDefinition.id === ALTER_CAVE_B3_INTRO_MAP_ID
      && !isSavedEventFlagEnabled(store.getState().saveEnvelope, ALTER_CAVE_B3_INTRO_EVENT_FLAG)
    ) {
      mapStatus.textContent = "洞窟の奥から不気味な気配がする……。";
    }
    if (resumeFromSavedPosition) {
      sessionStorage.removeItem(BATTLE_RETURN_CONTEXT_KEY);
      patchMapMenuState({ map_return_pending: false });
      if (returningFromBattle) {
        mapState = {
          ...mapState,
          steps_since_reset: 0,
        };
      }
    }
    if (postBattleEventFlags.length) {
      persistNamedEventFlags(postBattleEventFlags);
    }
    if (!canOccupyCurrentTravelMode(mapDefinition, mapState, store.getState().saveEnvelope)) {
      mapState = applyResolvedAirshipState(mapDefinition, {
        current_map_id: mapDefinition.id,
        tile_x: mapDefinition.spawn.x,
        tile_y: mapDefinition.spawn.y,
        current_movement_plane: normalizeMovementPlane(mapState?.current_movement_plane, "ground"),
        facing_direction: playerDirection,
        steps_since_reset: 0,
        switch_states: normalizeSwitchStates(mapState?.switch_states),
        opened_treasures: normalizeTreasureStates(mapState?.opened_treasures),
      }, store.getState().menuState, store.getState().saveEnvelope);
    }
    renderMapTiles(mapLayer, mapDefinition, store.getState().saveEnvelope);
    startNpcAnimation();
    persistCurrentMapState(mapState);
    setVisualMapPosition(mapState.tile_x, mapState.tile_y);
    syncMapBgm();
    const standingEventOnMount = findStandingEventTrigger(
      mapDefinition,
      mapState,
      store.getState().saveEnvelope,
    );
    if (standingEventOnMount) {
      await triggerStandingEvent(standingEventOnMount);
      return () => {
        confirmBtn.removeEventListener("click", onConfirm);
        cancelBtn.removeEventListener("click", onCancel);
        locationBtn.removeEventListener("click", onGoLocation);
        menuBtn.removeEventListener("click", onGoMenu);
        battleBtn.removeEventListener("click", onGoBattle);
        mapEventCloseBtn.removeEventListener("click", onCloseEvent);
        padButtons.forEach((button) => {
          const handlers = padHandlers.get(button);
          if (!handlers) return;
          button.removeEventListener("pointerdown", handlers.onPointerDown);
          button.removeEventListener("pointerup", handlers.onPointerUp);
          button.removeEventListener("pointercancel", handlers.onPointerUp);
          button.removeEventListener("pointerleave", handlers.onPointerLeave);
        });
        holdRepeater.stop();
        stopNpcAnimation();
        stopMapBgm();
        window.removeEventListener("keydown", onKeyDown);
      };
    }
    if (postBattleOverlayIndices.length || postBattleShowOpeningStory) {
      await openPostBattleDialogueSequence(postBattleOverlayIndices, {
        showOpeningStory: postBattleShowOpeningStory,
      });
      mapStatus.textContent = "戦いのあと、クリスタルが静かに輝いている。";
    } else if (postBattleCutsceneId) {
      await runPostBattleCutscene(postBattleCutsceneId);
    } else if (postBattleTreasureResult?.opened) {
      mapStatus.textContent = treasureGainStatusText(postBattleTreasureResult);
    } else {
      mapStatus.textContent = resumeFromSavedPosition
        ? `戦闘前の位置から再開しました。エンカウント率 ${(mapDefinition.encounterRate * 100).toFixed(0)}%。`
        : `方向ボタンかキーボード矢印キーで移動できます。エンカウント率 ${(mapDefinition.encounterRate * 100).toFixed(0)}%。`;
    }

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => redraw());
      resizeObserver.observe(mapViewport);
    } else {
      window.addEventListener("resize", redraw);
    }
  } catch (error) {
    mapStatus.textContent = `マップ読込失敗: ${String(error)}`;
  }

  return () => {
    confirmBtn.removeEventListener("click", onConfirm);
    cancelBtn.removeEventListener("click", onCancel);
    locationBtn.removeEventListener("click", onGoLocation);
    menuBtn.removeEventListener("click", onGoMenu);
    battleBtn.removeEventListener("click", onGoBattle);
    mapEventCloseBtn.removeEventListener("click", onCloseEvent);
    padButtons.forEach((button) => {
      const handlers = padHandlers.get(button);
      if (!handlers) return;
      button.removeEventListener("pointerdown", handlers.onPointerDown);
      button.removeEventListener("pointerup", handlers.onPointerUp);
      button.removeEventListener("pointercancel", handlers.onPointerUp);
      button.removeEventListener("pointerleave", handlers.onPointerLeave);
    });
    holdRepeater.stop();
    stopNpcAnimation();
    stopMoveAnimation();
    stopSaraFollowerMoveAnimation();
    stopCutsceneRingAnimation();
    stopAirshipCrashAnimation(mapLayer);
    stopMapBgm();
    window.removeEventListener("keydown", onKeyDown);
    if (resizeObserver) {
      resizeObserver.disconnect();
    } else {
      window.removeEventListener("resize", redraw);
    }
  };
}
