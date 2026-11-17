// A made-up home for the demo of the editor (`make demo`): states that the example router.yaml files find, the
// services a topic may fetch and what they return. Nothing here is a real home.

const state = (value, attributes = {}) => ({ state: value, attributes });

const POLISH = {
  "person.tomek": state("home", { friendly_name: "Tomek" }),
  "person.ania": state("not_home", { friendly_name: "Ania" }),
  "person.ola": state("Szkoła", { friendly_name: "Ola" }),
  "person.kuba": state("home", { friendly_name: "Kuba" }),
  "weather.dom": state("cloudy", { friendly_name: "Dom", temperature: 7, humidity: 81 }),
  "sensor.balkon_temperatura": state("6.8", { friendly_name: "Balkon temperatura", device_class: "temperature", unit_of_measurement: "°C" }),
  "sensor.balkon_wilgotnosc": state("83", { friendly_name: "Balkon wilgotność", device_class: "humidity", unit_of_measurement: "%" }),
  "sensor.salon_temperatura": state("21.4", { friendly_name: "Salon temperatura", device_class: "temperature", unit_of_measurement: "°C" }),
  "sensor.salon_co2": state("640", { friendly_name: "Salon CO2", device_class: "carbon_dioxide", unit_of_measurement: "ppm" }),
  "light.salon": state("on", { friendly_name: "Salon" }),
  "light.kuchnia": state("off", { friendly_name: "Kuchnia" }),
  "light.pokoj_oli": state("on", { friendly_name: "Pokój Oli" }),
  "light.tablet_ekran": state("on", { friendly_name: "Tablet ekran" }),
  "binary_sensor.drzwi_wejsciowe": state("off", { friendly_name: "Drzwi wejściowe", device_class: "door" }),
  "binary_sensor.salon_okno": state("on", { friendly_name: "Salon okno", device_class: "window" }),
  "binary_sensor.korytarz_ruch": state("off", { friendly_name: "Korytarz ruch", device_class: "motion" }),
  "cover.salon_roleta": state("open", { friendly_name: "Salon roleta" }),
  "climate.salon": state("heat", { friendly_name: "Salon", current_temperature: 21.4, temperature: 22 }),
  "media_player.salon_glosnik": state("playing", { friendly_name: "Salon głośnik" }),
  "media_player.kuchnia_glosnik": state("off", { friendly_name: "Kuchnia głośnik" }),
  "sensor.pralka_stan": state("Pranie", { friendly_name: "Pralka stan" }),
  "sensor.pralka_koniec": state("14:35", { friendly_name: "Pralka koniec" }),
  "vacuum.odkurzacz": state("docked", { friendly_name: "Odkurzacz" }),
  "sensor.plan_lekcji": state("5", { friendly_name: "Plan lekcji", ola: { poniedzialek: ["matematyka", "polski", "WF"] } }),
  "sensor.obowiazki": state("3", { friendly_name: "Obowiązki", kuba: ["wynieść śmieci"], ola: ["nakarmić kota"] }),
  "todo.zakupy": state("2", { friendly_name: "Zakupy" }),
  "sensor.wywoz_smieci": state("2026-11-17", { friendly_name: "Wywóz śmieci", device_class: "date", rodzaj: "plastik i metal" }),
  "sensor.wywoz_smieci_bio": state("2026-11-19", { friendly_name: "Wywóz śmieci bio", device_class: "date", rodzaj: "bio" }),
  "switch.lodowka": state("on", { friendly_name: "Lodówka" }),
  "calendar.rodzina": state("off", { friendly_name: "Rodzina" }),
  "calendar.praca_tomka": state("on", { friendly_name: "Praca Tomka" }),
  "calendar.urodziny": state("off", { friendly_name: "Urodziny" }),
};

const ENGLISH = Object.fromEntries(
  Object.entries({
    "person.tom": state("home", { friendly_name: "Tom" }),
    "person.ann": state("not_home", { friendly_name: "Ann" }),
    "weather.home": state("cloudy", { friendly_name: "Home", temperature: 7 }),
    "sensor.balcony_temperature": state("6.8", { friendly_name: "Balcony temperature", device_class: "temperature" }),
    "sensor.balcony_humidity": state("83", { friendly_name: "Balcony humidity", device_class: "humidity" }),
    "light.living_room": state("on", { friendly_name: "Living room" }),
    "light.kitchen": state("off", { friendly_name: "Kitchen" }),
    "light.tablet_screen": state("on", { friendly_name: "Tablet screen" }),
    "binary_sensor.front_door": state("off", { friendly_name: "Front door", device_class: "door" }),
    "binary_sensor.living_room_window": state("on", { friendly_name: "Living room window", device_class: "window" }),
    "media_player.living_room_speaker": state("playing", { friendly_name: "Living room speaker" }),
    "sensor.washing_machine_state": state("Washing", { friendly_name: "Washing machine" }),
    "sensor.school_timetable": state("5", { friendly_name: "School timetable", olivia: { monday: ["maths", "PE"] } }),
    "todo.shopping": state("2", { friendly_name: "Shopping" }),
    "sensor.bin_collection": state("2026-11-17", { friendly_name: "Bin collection", device_class: "date", kind: "plastic and metal" }),
    "switch.fridge": state("on", { friendly_name: "Fridge" }),
    "calendar.family": state("off", { friendly_name: "Family" }),
    "calendar.tom_work": state("on", { friendly_name: "Tom's work" }),
  }),
);

const FETCHED = {
  pl: {
    "calendar.get_events": ["Kalendarz: 16:00 Basen (Ola), 18:30 Zebranie w szkole"],
    "weather.get_forecasts": ["Prognoza: dziś 8°C, po południu deszcz; jutro 5°C, pochmurno"],
  },
  en: {
    "calendar.get_events": ["Calendar: 16:00 Swimming (Olivia), 18:30 School meeting"],
    "weather.get_forecasts": ["Forecast: today 8°C, rain in the afternoon; tomorrow 5°C, cloudy"],
  },
};

// What the tester of the demo says: sentences Home Assistant knows itself and the answers of some topics.
const TESTER = {
  pl: {
    haKnows: ["włącz światło w salonie", "zgaś światło w kuchni"],
    answers: {
      pogoda: "Dziś pochmurno, 7 stopni, po południu deszcz. Weź parasol.",
      kalendarz: "Dziś o 16:00 Ola ma basen, a o 18:30 jest zebranie w szkole.",
      pranie: "Pralka pierze, skończy o 14:35.",
      smieci: "Śmieciarka przyjedzie w poniedziałek 17 listopada po plastik i metal, a w środę po bio.",
    },
  },
  en: {
    haKnows: ["turn on the living room light", "turn off the kitchen light"],
    answers: {
      weather: "Cloudy today, 7 degrees, rain in the afternoon. Take an umbrella.",
      bins: "The bin lorry comes on Monday the 17th for plastic and metal.",
    },
  },
};

// The log of unrecognized commands and the test set of the demo.
const sentence = (text, count, last, route = "") => ({
  key: text.toLowerCase().replace(/[?.!]+$/, ""),
  text,
  count,
  first: "2026-11-01 08:00:00",
  last,
  kinds: ["no_intent_match"],
  speakers: [],
  areas: [],
  route,
  response: "",
});
const LEARN = {
  pl: {
    log: [
      sentence("Czy wziąć parasol?", 4, "2026-11-12 07:40:00", "pogoda"),
      sentence("Kiedy przyjedzie śmieciarka?", 2, "2026-11-11 19:02:00"),
      sentence("Ile prądu zużyliśmy wczoraj?", 1, "2026-11-10 21:15:00", "inne"),
    ],
    sentences: [
      {
        language: "pl",
        name: "swiatla.yaml",
        text: 'language: pl\nintents:\n  HassTurnOn:\n    data:\n      - sentences:\n          - "rozbudź {name}"\n          - "zapal (lampę|światło) {name}"\nresponses:\n  intents:\n    HassTurnOn:\n      default: Już świeci.\n',
      },
    ],
    tests: [
      { sentence: "Czy jutro będzie padać?", topic: "pogoda" },
      { sentence: "Czy pralka skończyła?", topic: "pranie" },
      { sentence: "włącz światło w salonie", intent: "HassTurnOn" },
    ],
  },
  en: {
    log: [
      sentence("Do I need an umbrella?", 3, "2026-11-12 07:40:00", "weather"),
      sentence("When do the bins go out?", 2, "2026-11-11 19:02:00"),
    ],
    tests: [{ sentence: "Will it rain tomorrow?", topic: "weather" }],
  },
};

/** The demo home in a language: `{ states, services, fetched, areas, haKnows, answers, log, tests }`. */
export function demoHome(language) {
  const areas = (language === "en" ? ["Living room", "Kitchen", "Bedroom"] : ["Salon", "Kuchnia", "Sypialnia", "Pokój Oli", "Pokój Kuby"])
    .map((name) => ({ area_id: name.toLowerCase().replace(/\W+/g, "_"), name }));
  return {
    language: language === "en" ? "en" : "pl",
    states: language === "en" ? ENGLISH : POLISH,
    services: { "calendar.get_events": "read_only", "weather.get_forecasts": "read_only", "todo.get_items": "read_only", "light.turn_on": "changes" },
    fetched: FETCHED[language === "en" ? "en" : "pl"],
    areas: Object.fromEntries(areas.map((area) => [area.area_id, area])),
    ...TESTER[language === "en" ? "en" : "pl"],
    ...LEARN[language === "en" ? "en" : "pl"],
  };
}
