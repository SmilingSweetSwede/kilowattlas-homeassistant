// The Kilowattlas status page and card, and the logo as a sidebar icon.
// Plain custom elements with Home Assistant's own theme variables. Everything
// shown comes from the websocket subscription kilowattlas/subscribe_status
// (panel.py), which pushes each change as soon as a reading is acknowledged.

const LOGO =
  "M2.25 19.2a.7.7 0 0 1 .7-.7h2.75a.7.7 0 0 1 .7.7v2.2a.7.7 0 0 1-.7.7H2.95a.7.7 0 0 1-.7-.7z" +
  "M7.5 14.7a.7.7 0 0 1 .7-.7h2.7a.7.7 0 0 1 .7.7v6.7a.7.7 0 0 1-.7.7H8.2a.7.7 0 0 1-.7-.7z" +
  "M12.6 16.8a.7.7 0 0 1 .7-.7H16a.7.7 0 0 1 .7.7v4.6a.7.7 0 0 1-.7.7h-2.7a.7.7 0 0 1-.7-.7z" +
  "M17.6 9.8a.7.7 0 0 1 .7-.7h2.75a.7.7 0 0 1 .7.7v11.6a.7.7 0 0 1-.7.7H18.3a.7.7 0 0 1-.7-.7z" +
  "M2.6 17.6 12.65 5.15l1.4 4.05 7.35-7.15-8.75 12.95-1.2-5.15z";

// Material Design Icons (Apache-2.0): github, facebook.
const GITHUB_ICON =
  "M12,2A10,10 0 0,0 2,12C2,16.42 4.87,20.17 8.84,21.5C9.34,21.58 9.5,21.27 9.5,21C9.5,20.77 9.5,20.14 9.5,19.31C6.73,19.91 6.14,17.97 6.14,17.97C5.68,16.81 5.03,16.5 5.03,16.5C4.12,15.88 5.1,15.9 5.1,15.9C6.1,15.97 6.63,16.93 6.63,16.93C7.5,18.45 8.97,18 9.54,17.76C9.63,17.11 9.89,16.67 10.17,16.42C7.95,16.17 5.62,15.31 5.62,11.5C5.62,10.39 6,9.5 6.65,8.79C6.55,8.54 6.2,7.5 6.75,6.15C6.75,6.15 7.59,5.88 9.5,7.17C10.29,6.95 11.15,6.84 12,6.84C12.85,6.84 13.71,6.95 14.5,7.17C16.41,5.88 17.25,6.15 17.25,6.15C17.8,7.5 17.45,8.54 17.35,8.79C18,9.5 18.38,10.39 18.38,11.5C18.38,15.32 16.04,16.16 13.81,16.41C14.17,16.72 14.5,17.33 14.5,18.26C14.5,19.6 14.5,20.68 14.5,21C14.5,21.27 14.66,21.59 15.17,21.5C19.14,20.16 22,16.42 22,12A10,10 0 0,0 12,2Z";
const FACEBOOK_ICON =
  "M12 2.04C6.5 2.04 2 6.53 2 12.06C2 17.06 5.66 21.21 10.44 21.96V14.96H7.9V12.06H10.44V9.85C10.44 7.34 11.93 5.96 14.22 5.96C15.31 5.96 16.45 6.15 16.45 6.15V8.62H15.19C13.95 8.62 13.56 9.39 13.56 10.18V12.06H16.57V14.96H13.56V21.96A10 10 0 0 0 22 12.06C22 6.53 17.5 2.04 12 2.04Z";

window.customIcons = window.customIcons || {};
window.customIcons.kilowattlas = {
  getIcon: async () => ({ path: LOGO, viewBox: "0 0 24 24" }),
};

// Right after the integration is set up, Home Assistant adds the sidebar entry
// and loads this file at the same time. A sidebar that is drawn first asks for
// "kilowattlas:logo" before the lines above have run. <ha-icon> then decides
// that the name belongs to an old-style icon set and keeps drawing it that
// way, also when it is given the same name again: the entry stayed without
// its logo until the page was loaded again. The only thing that makes
// <ha-icon> change its mind is being given a Material Design icon. So every
// <ha-icon> already showing one of our icons gets one for a moment, and then
// its own name back.
const ICON_PREFIX = "kilowattlas:";
const RESET_ICON = "mdi:circle-small";
const MAX_SHADOW_DEPTH = 12;

function redrawIcons(root, depth) {
  for (const node of root.querySelectorAll("*")) {
    // Only an icon stuck in the old-style mode: one that already shows the
    // logo is left alone, so a normal page load never makes it flicker.
    if (
      node.localName === "ha-icon" &&
      typeof node.icon === "string" &&
      node.icon.startsWith(ICON_PREFIX) &&
      node._legacy !== false
    ) {
      const name = node.icon;
      node.icon = RESET_ICON;
      Promise.resolve(node.updateComplete).then(() => {
        if (node.icon === RESET_ICON) node.icon = name;
      });
    }
    if (node.shadowRoot && depth < MAX_SHADOW_DEPTH) redrawIcons(node.shadowRoot, depth + 1);
  }
}

// Now, and once more for a sidebar entry drawn while this file was loading. An
// icon created after that finds the logo by itself.
for (const delay of [0, 1500]) {
  setTimeout(() => {
    try {
      redrawIcons(document, 0);
    } catch (err) {
      // The logo is decoration: never let it stop the page.
    }
  }, delay);
}

const TICK_MS = 1000;
// A change made on the map shows up here while the page is open.
const DETAILS_REFRESH_MS = 30000;
const DISCUSSIONS_URL = "https://github.com/SmilingSweetSwede/kilowattlas-homeassistant/discussions/1";
const FACEBOOK_URL = "https://www.facebook.com/groups/samnatet";
const CONTACT_EMAIL = "admin@kilowattlas.com";
const CONTACT_PHONE = "+46725711065";
const CONTACT_PHONE_SHOWN = "+46 72 571 10 65";

const TEXT = {
  sv: {
    title: "Kilowattlas",
    connected: "Ansluten",
    retrying: "Anslutningsfel, försöker igen",
    revoked: "Frånkopplad, åtkomsten är återkallad",
    starting: "Startar",
    not_loaded: "Inte igång",
    channels: "Delar",
    channelsUnit: "kanaler",
    lastSent: "Senast skickat",
    never: "Inte än",
    queued: "Väntar i kö",
    catchingUp: "Skickar ikapp från recordern",
    rejected: "Avvisade i senaste sändningen",
    openMap: "Öppna kartan",
    emptyTitle: "Inget delas ännu",
    emptyText: "Kilowattlas hittar inga effektsensorer. Ställ in dem i Energi-panelen, eller ange dem direkt i integrationen under Konfigurera.",
    setupEnergy: "Ställ in Energi-panelen",
    setupManual: "Ange sensorer i Kilowattlas",
    allUnticked: "Inget delas, alla kanaler är avmarkerade",
    detailsTitle: "Din anläggning",
    detailsHelp: "Samma uppgifter som under Redigera min anläggning på kartan. Ändrar du på ett ställe syns det på det andra.",
    save: "Spara",
    saved: "Sparat",
    saveDetailsFailed: "Kunde inte spara. Kontrollera anslutningen och försök igen.",
    loadDetailsFailed: "Kunde inte hämta uppgifterna från Kilowattlas.",
    conflict: "Uppgifterna har ändrats på kartan sedan du öppnade dem. Hämta de senaste och gör din ändring igen.",
    fetchLatest: "Hämta de senaste",
    invalid: {
      value_out_of_range: "Något värde är utanför det tillåtna intervallet.",
      field_too_long: "Någon text är för lång.",
      capacity_requires_review: "Så stor ändring av effekten kräver granskning. Ändra den på kartan i stället.",
      invalid_mount_type: "Välj en monteringstyp i listan.",
    },
    invalidOther: "Servern godtog inte värdena.",
    rooftop: "Tak",
    ground: "Mark",
    fields: {
      name: "Namn",
      capacity_kw: "Installerad effekt (kW)",
      mount_type: "Montering",
      install_year: "Installationsår",
      panel_make: "Paneler, märke",
      panel_count: "Antal paneler",
      inverter_make: "Växelriktare, märke",
      roof_tilt_deg: "Lutning (grader, 0 = platt)",
      roof_azimuth_deg: "Riktning (grader, 0 = norr, 180 = söder)",
      battery_kwh: "Batteristorlek (kWh)",
    },
    readings: "Det här delas",
    readingsHelp: "Avmarkerar du en kanal lämnar den aldrig Home Assistant. Markerar du den igen börjar den med nästa mätning.",
    sent: "Senast skickat värde",
    notSent: "Inte skickat än",
    offOnWeb: "Avstängd på kartan",
    saveFailed: "Kunde inte spara valet.",
    import: "import",
    export: "export",
    charging: "laddar",
    discharging: "laddar ur",
    kinds: {
      gross_production: "Sol",
      grid_power: "Nät",
      net_export: "Nät",
      battery_power: "Batteri",
      battery_soc: "Laddnivå",
      consumption: "Hem",
      ev_charger_power: "Elbilsladdare",
      heat_pump_power: "Värmepump",
      device_power: "Enhet",
    },
    communityTitle: "Var med och bygg energigemenskaper",
    communityText: "Kilowattlas utvecklar en lösning som ska göra det möjligt att bilda energigemenskaper. Från den 1 januari 2027 får hushåll i samma elområde dela el med varandra. Var med och påverka hur det ska fungera.",
    fundText: "Är du intresserad? Vi vill också diskutera förutsättningarna för en elhandelsfond för småsparare. Det finns ingen sådan fond i dag, och det här är inget erbjudande.",
    contact: "Hör gärna av dig om du har frågor:",
    contactPhone: "tel",
    discuss: "Delta i diskussionen",
    facebook: "Facebook-gruppen",
    aboutTitle: "Vad är en energigemenskap och ett cVPP?",
    about: [
      "Energigemenskap: hushåll i samma elområde delar el med varandra, vilket blir tillåtet från den 1 januari 2027 (prop. 2025/26:240).",
      "cVPP (community virtual power plant): ett virtuellt kraftverk som ägs av medlemmarna. Hushållens batterier och annan flexibel utrustning samlas och säljer flexibilitet till Svenska kraftnät eller nätägaren, och intäkterna går tillbaka till hushållen.",
      "Kilowattlas mäter, räknar och organiserar. Integrationen styr aldrig din utrustning, och att vara med i en gemenskap är ett separat val på kilowattlas.com.",
    ],
    aboutLink: "Läs mer och anmäl intresse",
    none: "Kilowattlas är inte konfigurerat.",
    failed: "Kunde inte hämta status.",
    ago: (s) => `för ${s} sedan`,
    now: "nyss",
  },
  en: {
    title: "Kilowattlas",
    connected: "Connected",
    retrying: "Connection error, retrying",
    revoked: "Disconnected, access revoked",
    starting: "Starting",
    not_loaded: "Not running",
    channels: "Sharing",
    channelsUnit: "channels",
    lastSent: "Last sent",
    never: "Not yet",
    queued: "Queued",
    catchingUp: "Catching up from the recorder",
    rejected: "Rejected in the last batch",
    openMap: "Open the map",
    emptyTitle: "Nothing is shared yet",
    emptyText: "Kilowattlas finds no power sensors. Set them up in the Energy dashboard, or enter them in the integration under Configure.",
    setupEnergy: "Set up the Energy dashboard",
    setupManual: "Enter sensors in Kilowattlas",
    allUnticked: "Nothing is shared, every channel is unticked",
    detailsTitle: "Your installation",
    detailsHelp: "The same details as Edit my plant on the map. A change in one place shows in the other.",
    save: "Save",
    saved: "Saved",
    saveDetailsFailed: "Could not save. Check the connection and try again.",
    loadDetailsFailed: "Could not load the details from Kilowattlas.",
    conflict: "The details changed on the map since you opened them. Fetch the latest and make your change again.",
    fetchLatest: "Fetch the latest",
    invalid: {
      value_out_of_range: "A value is outside the allowed range.",
      field_too_long: "A text is too long.",
      capacity_requires_review: "A change of capacity this large needs review. Change it on the map instead.",
      invalid_mount_type: "Choose a mounting type from the list.",
    },
    invalidOther: "The server did not accept the values.",
    rooftop: "Roof",
    ground: "Ground",
    fields: {
      name: "Name",
      capacity_kw: "Installed capacity (kW)",
      mount_type: "Mounting",
      install_year: "Installation year",
      panel_make: "Panel make",
      panel_count: "Number of panels",
      inverter_make: "Inverter make",
      roof_tilt_deg: "Tilt (degrees, 0 = flat)",
      roof_azimuth_deg: "Facing (degrees, 0 = north, 180 = south)",
      battery_kwh: "Battery size (kWh)",
    },
    readings: "What is shared",
    readingsHelp: "An unticked channel never leaves Home Assistant. Ticked again, it starts with its next reading.",
    sent: "Last value sent",
    notSent: "Not sent yet",
    offOnWeb: "Off on the map",
    saveFailed: "Could not save the choice.",
    import: "import",
    export: "export",
    charging: "charging",
    discharging: "discharging",
    kinds: {
      gross_production: "Solar",
      grid_power: "Grid",
      net_export: "Grid",
      battery_power: "Battery",
      battery_soc: "State of charge",
      consumption: "Home",
      ev_charger_power: "EV charger",
      heat_pump_power: "Heat pump",
      device_power: "Device",
    },
    communityTitle: "Help build energy communities",
    communityText: "Kilowattlas is developing a solution to make it possible to form energy communities. From 1 January 2027, households in the same bidding zone may share electricity with each other. Help shape how it should work.",
    fundText: "Interested? We also want to discuss what it would take to set up an electricity trading fund for small savers. No such fund exists today, and this is not an offer.",
    contact: "Please reach out if you have any questions:",
    contactPhone: "tel",
    discuss: "Join the discussion",
    facebook: "Facebook group (in Swedish)",
    aboutTitle: "What are energy communities and cVPPs?",
    about: [
      "Energy community: households in the same bidding zone share electricity with each other, allowed from 1 January 2027 (prop. 2025/26:240).",
      "cVPP (community virtual power plant): a virtual power plant owned by its members. Households' batteries and other flexible equipment are pooled to sell flexibility to Svenska kraftnät or the grid operator, with the proceeds going back to the households.",
      "Kilowattlas measures, counts and organises. This integration never controls your equipment, and joining a community is a separate choice on kilowattlas.com.",
    ],
    aboutLink: "Read more and sign up",
    none: "Kilowattlas is not configured.",
    failed: "Could not load the status.",
    ago: (s) => `${s} ago`,
    now: "just now",
  },
};

const STYLE = `
  :host { display: block; container-type: inline-size; }
  /* One column in reading order; beside each other when there is room. */
  .layout { display: grid; gap: 16px; align-items: start; }
  .layout + .layout { margin-top: 16px; }
  .slot-channels:empty { display: none; }
  @container (min-width: 820px) {
    .layout {
      grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
      grid-template-rows: auto auto 1fr;
    }
    .slot-status { grid-column: 1; grid-row: 1; }
    .slot-community { grid-column: 2; grid-row: 1 / span 3; }
    .slot-channels { grid-column: 1; grid-row: 2; }
    .slot-details { grid-column: 1; grid-row: 3; }
    .slot-channels:empty + .slot-details { grid-row: 2; }
  }
  .card {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    color: var(--primary-text-color);
    padding: 16px;
  }
  .message + .message { margin-top: 16px; }
  h2 { margin: 0 0 12px; font-size: var(--ha-card-header-font-size, 24px); font-weight: 400; }
  .status { display: flex; align-items: center; gap: 8px; font-size: 16px; margin-bottom: 12px; }
  .dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .dot.ok { background: var(--success-color, #4caf50); }
  .dot.warn { background: var(--warning-color, #ff9800); }
  .dot.bad { background: var(--error-color, #f44336); }
  .row { display: flex; justify-content: space-between; gap: 16px; padding: 4px 0; color: var(--secondary-text-color); }
  .row b { color: var(--primary-text-color); font-weight: 500; }
  .map {
    display: inline-block; margin-top: 12px; padding: 8px 14px; border-radius: 8px;
    color: var(--primary-color); border: 1px solid var(--primary-color); text-decoration: none;
  }
  .note { margin: 12px 0 0; font-size: 13px; color: var(--secondary-text-color); }
  /* The house from the map (kilowattlas-figure.js), in Home Assistant's colours. */
  .figure { margin: 12px 0; }
  .links { display: flex; flex-wrap: wrap; gap: 10px; }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 4px; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  .field input, .field select {
    font: inherit; font-size: 15px; padding: 8px 10px; border-radius: 6px; box-sizing: border-box; width: 100%;
    color: var(--primary-text-color); background: var(--secondary-background-color, transparent);
    border: 1px solid var(--divider-color, #888);
  }
  .field input:focus-visible, .field select:focus-visible, .save:focus-visible {
    outline: 2px solid var(--primary-color); outline-offset: 1px;
  }
  .save-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 14px; }
  .save {
    font: inherit; font-weight: 500; padding: 8px 20px; border: none; border-radius: 8px; cursor: pointer;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
  }
  .save:disabled { opacity: 0.45; cursor: default; }
  .save.quiet { background: none; color: var(--primary-color); border: 1px solid var(--primary-color); }
  .save-state { font-size: 13px; color: var(--secondary-text-color); }
  .save-state.bad { color: var(--error-color, #f44336); }
  h3 { margin: 0 0 4px; font-size: 16px; font-weight: 500; }
  h3 + .note { margin: 4px 0 12px; }
  .channel {
    display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 2px 12px;
    padding: 10px 0; border-top: 1px solid var(--divider-color, #e0e0e0);
  }
  .channel input { width: 18px; height: 18px; margin: 0; accent-color: var(--primary-color); cursor: pointer; }
  .channel input:disabled { cursor: default; }
  .channel .name { font-weight: 500; }
  .channel .value { text-align: right; font-weight: 500; font-variant-numeric: tabular-nums; }
  .channel .sensor, .channel .when {
    font-size: 12px; color: var(--secondary-text-color); grid-row: 2;
  }
  .channel .sensor { grid-column: 2; }
  .channel .when { grid-column: 3; text-align: right; }
  .channel.off .name, .channel.off .value { color: var(--secondary-text-color); }
  .error { margin: 8px 0 0; font-size: 13px; color: var(--error-color, #f44336); }
  /* The logo's colours, dark enough for white text in both themes. */
  .community {
    background: linear-gradient(135deg, #6d28d9 0%, #2563eb 55%, #0e7490 100%);
    border: none; color: #fff; padding: 20px;
  }
  .community-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .community-head svg { width: 36px; height: 36px; flex: none; fill: #fff; }
  .community h3 { margin: 0; font-size: 20px; font-weight: 600; line-height: 1.25; }
  .community > p { margin: 0 0 12px; font-size: 15px; line-height: 1.5; }
  .community > .actions { margin-top: 16px; }
  .community > .contact { font-size: 14px; }
  .community > .contact a { color: #fff; font-weight: 600; }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
  .action {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 16px; border-radius: 8px; font-weight: 600; text-decoration: none;
    border: 1px solid #fff; color: #fff;
  }
  .action svg { width: 20px; height: 20px; flex: none; fill: currentColor; }
  .action.primary { background: #fff; color: #4c1d95; }
  .action:hover { filter: brightness(0.93); }
  details summary { cursor: pointer; font-size: 14px; font-weight: 500; }
  details p { margin: 10px 0 0; font-size: 14px; line-height: 1.45; }
  details a { display: inline-block; margin-top: 10px; color: #fff; }
`;

function statusDot(status) {
  if (status === "connected") return "ok";
  return status === "revoked" ? "bad" : "warn";
}

function age(iso, t) {
  if (!iso) return t.never;
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 1) return t.now;
  if (s < 60) return t.ago(`${s} s`);
  if (s < 3600) return t.ago(`${Math.floor(s / 60)} min`);
  return t.ago(`${Math.floor(s / 3600)} h`);
}

// Signs are the Energy dashboard's: grid positive = import, battery positive = discharging.
function formatValue(channel, t) {
  const v = channel.last_value;
  if (v === null || v === undefined) return "–";
  if (channel.percent) return `${Math.round(v)} %`;
  const kw = `${Math.abs(v).toFixed(2)} kW`;
  if (channel.kind === "grid_power" && Math.abs(v) >= 0.005) {
    return `${v > 0 ? t.import : t.export} ${kw}`;
  }
  if (channel.kind === "battery_power" && Math.abs(v) >= 0.01) {
    return `${kw} · ${v > 0 ? t.discharging : t.charging}`;
  }
  return kw;
}

function svgIcon(d) {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", d);
  icon.append(path);
  return icon;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const DETAIL_FIELDS = [
  { key: "name", type: "text" },
  { key: "capacity_kw", type: "number", min: 0, step: "any" },
  { key: "mount_type", type: "select", options: ["rooftop", "ground"] },
  { key: "install_year", type: "number", min: 1950, max: 2100, step: "1" },
  { key: "panel_make", type: "text" },
  { key: "panel_count", type: "number", min: 1, max: 10000, step: "1" },
  { key: "inverter_make", type: "text" },
  { key: "roof_tilt_deg", type: "number", min: 0, max: 90, step: "1" },
  { key: "roof_azimuth_deg", type: "number", min: 0, max: 360, step: "1" },
  { key: "battery_kwh", type: "number", min: 0, max: 1000, step: "any" },
];

class KilowattlasStatusCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    this._body = el("div");
    this.shadowRoot.append(style, this._body);
  }

  setConfig() {}

  getCardSize() {
    return 4;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._subscribed && this.isConnected) this._start();
  }

  connectedCallback() {
    if (this._hass && !this._subscribed) this._start();
    // A redraw between press and release would lose the click.
    this._body.addEventListener("pointerdown", this._onPress);
    window.addEventListener("pointerup", this._onRelease);
  }

  disconnectedCallback() {
    clearInterval(this._ticker);
    clearInterval(this._detailsTimer);
    this._body.removeEventListener("pointerdown", this._onPress);
    window.removeEventListener("pointerup", this._onRelease);
    this._subscribed?.then((unsubscribe) => unsubscribe()).catch(() => {});
    this._subscribed = undefined;
  }

  _start() {
    this._subscribed = this._hass.connection.subscribeMessage(
      (message) => this._render(message.entries),
      { type: "kilowattlas/subscribe_status" }
    );
    this._subscribed.catch(() => this._renderMessage(this._text.failed));
    this._ticker = setInterval(() => this._tick(), TICK_MS);
    this._detailsTimer = setInterval(() => {
      for (const form of this._forms?.values() ?? []) this._loadDetails(form, false);
    }, DETAILS_REFRESH_MS);
  }

  _onPress = () => {
    this._pressed = true;
  };

  _onRelease = () => {
    this._pressed = false;
    if (this._waiting) {
      const entries = this._waiting;
      this._waiting = undefined;
      this._render(entries);
    }
  };

  // Counts up between refreshes without redrawing, so a click is never lost.
  _tick() {
    const t = this._text;
    for (const node of this._body.querySelectorAll("[data-sent]")) {
      node.textContent = age(node.dataset.sent, t);
    }
  }

  async _setShared(entry, channel, shared) {
    this._error = "";
    try {
      await this._hass.callWS({
        type: "kilowattlas/set_shared",
        entry_id: entry.entry_id,
        channel_key: channel.key,
        shared,
      });
    } catch (_err) {
      this._error = this._text.saveFailed;
    }
  }

  get _text() {
    return TEXT[(this._hass?.language || "en").startsWith("sv") ? "sv" : "en"];
  }

  _renderMessage(message) {
    const card = el("div", "card message");
    card.append(el("h2", "", this._text.title), el("div", "", message));
    this._body.replaceChildren(card);
  }

  _render(entries) {
    if (this._pressed) {
      this._waiting = entries;
      return;
    }
    if (!entries.length) {
      this._renderMessage(this._text.none);
      return;
    }
    this._body.replaceChildren(
      ...entries.map((entry) => {
        const slots = this._slotsFor(entry);
        slots.status.replaceChildren(this._renderStatus(entry));
        slots.channels.replaceChildren(...(entry.channels.length ? [this._renderChannels(entry)] : []));
        return slots.layout;
      })
    );
  }

  // Only status and channels are redrawn on a push; the community card and the
  // form stay the same nodes, so nothing being typed or opened is lost.
  _slotsFor(entry) {
    this._slots = this._slots || new Map();
    let slots = this._slots.get(entry.entry_id);
    if (!slots) {
      slots = {
        layout: el("div", "layout"),
        status: el("div", "slot-status"),
        community: el("div", "slot-community"),
        channels: el("div", "slot-channels"),
        details: el("div", "slot-details"),
      };
      slots.community.append(this._renderCommunity(entry));
      slots.details.append(this._buildDetails(entry));
      slots.layout.append(slots.status, slots.community, slots.channels, slots.details);
      this._slots.set(entry.entry_id, slots);
    }
    return slots;
  }

  _renderStatus(entry) {
    const t = this._text;
    const card = el("div", "card");
    card.append(el("h2", "", t.title));

    const empty = entry.channels.length === 0;
    const nothing = entry.status === "connected" && (empty || entry.shared_channels === 0);
    const status = el("div", "status");
    status.append(
      el("span", `dot ${nothing ? "warn" : statusDot(entry.status)}`),
      el("span", "", nothing ? (empty ? t.emptyTitle : t.allUnticked) : t[entry.status] || entry.status)
    );
    card.append(status);

    if (empty) {
      card.append(el("p", "note", t.emptyText));
      const links = el("div", "links");
      const go = (label, href) => {
        const a = el("a", "map", label);
        a.href = href;
        return a;
      };
      links.append(
        go(t.setupEnergy, "/config/energy"),
        go(t.setupManual, "/config/integrations/integration/kilowattlas")
      );
      card.append(links);
      return card;
    }

    const row = (label, value, sent) => {
      const r = el("div", "row");
      const shown = el("b", "", value);
      if (sent) shown.dataset.sent = sent;
      r.append(el("span", "", label), shown);
      card.append(r);
    };
    row(t.channels, `${entry.shared_channels} ${t.channelsUnit}`);
    row(t.lastSent, age(entry.last_sent, t), entry.last_sent);
    row(t.queued, String(entry.queued));
    if (entry.catching_up) row(t.catchingUp, "…");
    if (entry.rejected) row(t.rejected, String(entry.rejected));

    if (entry.map_url) {
      const map = el("a", "map", `${t.openMap} →`);
      map.href = entry.map_url;
      map.target = "_blank";
      map.rel = "noopener noreferrer";
      card.append(map);
    }
    return card;
  }

  _buildDetails(entry) {
    const t = this._text;
    const card = el("div", "card");
    card.append(el("h3", "", t.detailsTitle), el("p", "note", t.detailsHelp));

    const form = document.createElement("form");
    const fields = el("div", "fields");
    const inputs = {};
    for (const field of DETAIL_FIELDS) {
      const label = el("label", "field");
      label.append(el("span", "", t.fields[field.key]));
      let input;
      if (field.type === "select") {
        input = document.createElement("select");
        input.append(el("option", "", ""));
        for (const value of field.options) {
          const option = el("option", "", t[value]);
          option.value = value;
          input.append(option);
        }
      } else {
        input = document.createElement("input");
        input.type = field.type;
        if (field.min !== undefined) input.min = field.min;
        if (field.max !== undefined) input.max = field.max;
        if (field.step) input.step = field.step;
      }
      inputs[field.key] = input;
      label.append(input);
      fields.append(label);
    }
    const button = el("button", "save", t.save);
    button.type = "submit";
    button.disabled = true;
    const state = el("span", "save-state");
    const refetch = el("button", "save quiet", t.fetchLatest);
    refetch.type = "button";
    refetch.hidden = true;
    const row = el("div", "save-row");
    row.append(button, refetch, state);
    const figure = el("div", "figure");
    form.append(figure, fields, row);
    card.append(form);

    const form_ = { entry, inputs, button, state, refetch, details: null, revision: null };
    this._mountFigure(form_, figure);
    (this._forms = this._forms || new Map()).set(entry.entry_id, form_);
    form.addEventListener("input", () => {
      this._updateFigure(form_);
      button.disabled = !this._isDirty(form_);
      state.textContent = "";
      state.className = "save-state";
    });
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      this._saveDetails(form_);
    });
    refetch.addEventListener("click", () => this._loadDetails(form_, true));
    this._loadDetails(form_, true);
    return card;
  }

  // The same drawing as Edit my plant on the map: <kilowattlas-figure> from
  // kilowattlas-figure.js, loaded with the same cache-busting query as this file.
  async _mountFigure(form, target) {
    try {
      const url = new URL(`kilowattlas-figure.js${new URL(import.meta.url).search}`, import.meta.url);
      await import(url.href);
      const figure = document.createElement("kilowattlas-figure");
      figure.setProps({
        ...this._figureProps(form),
        isSv: (this._hass?.language || "en").startsWith("sv"),
        interactive: true,
      });
      const set = (key) => (ev) => {
        form.inputs[key].value = String(Math.round(ev.detail));
        form.inputs[key].dispatchEvent(new Event("input", { bubbles: true }));
      };
      figure.addEventListener("tilt", set("roof_tilt_deg"));
      figure.addEventListener("azimuth", set("roof_azimuth_deg"));
      target.append(figure);
      form.figure = figure;
    } catch (_err) {
      // Without the drawing the fields below still do everything.
      target.remove();
    }
  }

  _figureProps(form) {
    const now = this._readForm(form);
    return {
      mount: now.mount_type,
      tilt: now.roof_tilt_deg,
      azimuth: now.roof_azimuth_deg,
      panels: now.panel_count,
    };
  }

  _updateFigure(form) {
    form.figure?.setProps(this._figureProps(form));
  }

  _readForm(form) {
    const out = {};
    for (const field of DETAIL_FIELDS) {
      const raw = form.inputs[field.key].value.trim();
      if (raw === "") out[field.key] = null;
      else if (field.type !== "number") out[field.key] = raw;
      else out[field.key] = field.step === "any" ? Number(raw) : Math.round(Number(raw));
    }
    return out;
  }

  _isDirty(form) {
    if (!form.details) return false;
    const now = this._readForm(form);
    return DETAIL_FIELDS.some((f) => (now[f.key] ?? null) !== (form.details[f.key] ?? null));
  }

  _applyDetails(form, details, revision) {
    form.details = details;
    form.revision = revision;
    for (const field of DETAIL_FIELDS) {
      const value = details[field.key];
      form.inputs[field.key].value = value === null || value === undefined ? "" : String(value);
    }
    form.button.disabled = true;
    this._updateFigure(form);
  }

  async _loadDetails(form, force) {
    if (!force && (document.hidden || this._isDirty(form))) return;
    try {
      const res = await this._hass.callWS({
        type: "kilowattlas/get_details",
        entry_id: form.entry.entry_id,
      });
      // Typing started while waiting for the answer: keep what is typed.
      if (!force && this._isDirty(form)) return;
      this._applyDetails(form, res.details, res.revision);
      if (force) this._setSaveState(form, "");
      form.refetch.hidden = true;
    } catch (_err) {
      if (force) this._setSaveState(form, this._text.loadDetailsFailed, true);
    }
  }

  _setSaveState(form, text, bad) {
    form.state.textContent = text;
    form.state.className = bad ? "save-state bad" : "save-state";
  }

  async _saveDetails(form) {
    const t = this._text;
    const next = { ...form.details, ...this._readForm(form) };
    // The compass point follows the degrees on the server; send it only if no
    // degrees were ever given, or clearing the degrees would bring them back.
    if (next.roof_azimuth_deg !== null || form.details.roof_azimuth_deg !== null) {
      next.roof_direction = null;
    }
    form.button.disabled = true;
    try {
      const res = await this._hass.callWS({
        type: "kilowattlas/save_details",
        entry_id: form.entry.entry_id,
        revision: form.revision,
        details: next,
      });
      if (res.conflict) {
        this._setSaveState(form, t.conflict, true);
        form.refetch.hidden = false;
      } else if (res.rejected) {
        this._setSaveState(form, t.invalid[res.rejected] || t.invalidOther, true);
        form.button.disabled = false;
      } else {
        this._applyDetails(form, res.details, res.revision);
        this._setSaveState(form, t.saved);
      }
    } catch (_err) {
      this._setSaveState(form, t.saveDetailsFailed, true);
      form.button.disabled = false;
    }
  }

  _renderChannels(entry) {
    const t = this._text;
    const card = el("div", "card");
    card.append(el("h3", "", t.readings), el("p", "note", t.readingsHelp));
    for (const channel of entry.channels) {
      const on = channel.shared && !channel.off_on_web;
      const row = el("div", on ? "channel" : "channel off");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = channel.shared;
      box.disabled = channel.off_on_web;
      box.setAttribute("aria-label", channel.name || t.kinds[channel.kind] || channel.kind);
      box.addEventListener("change", () => this._setShared(entry, channel, box.checked));
      const when = channel.off_on_web
        ? t.offOnWeb
        : channel.last_sent
          ? age(channel.last_sent, t)
          : t.notSent;
      const whenNode = el("span", "when", when);
      if (channel.last_sent && !channel.off_on_web) whenNode.dataset.sent = channel.last_sent;
      row.append(
        box,
        el("span", "name", channel.name || t.kinds[channel.kind] || channel.kind),
        el("span", "value", formatValue(channel, t)),
        el("span", "sensor", channel.sensor),
        whenNode
      );
      card.append(row);
    }
    if (this._error) card.append(el("p", "error", this._error));
    return card;
  }

  _renderCommunity(entry) {
    const t = this._text;
    const card = el("div", "card community");

    const head = el("div", "community-head");
    head.append(svgIcon(LOGO), el("h3", "", t.communityTitle));
    card.append(head, el("p", "", t.communityText), el("p", "", t.fundText));

    const link = (className, label, href, icon) => {
      const a = el("a", className, label);
      if (icon) a.prepend(svgIcon(icon));
      a.href = href;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return a;
    };
    const actions = el("div", "actions");
    actions.append(
      link("action primary", t.discuss, DISCUSSIONS_URL, GITHUB_ICON),
      link("action", t.facebook, FACEBOOK_URL, FACEBOOK_ICON)
    );
    card.append(actions);

    const contact = el("p", "contact", `${t.contact} `);
    const mail = el("a", "", CONTACT_EMAIL);
    mail.href = `mailto:${CONTACT_EMAIL}`;
    const phone = el("a", "", CONTACT_PHONE_SHOWN);
    phone.href = `tel:${CONTACT_PHONE}`;
    contact.append(mail, `, ${t.contactPhone} `, phone);
    card.append(contact);

    const details = document.createElement("details");
    details.open = this._aboutOpen === true;
    details.addEventListener("toggle", () => (this._aboutOpen = details.open));
    details.append(el("summary", "", t.aboutTitle));
    for (const paragraph of t.about) details.append(el("p", "", paragraph));
    details.append(link("", `${t.aboutLink} →`, entry.community_url));
    card.append(details);
    return card;
  }
}

class KilowattlasPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; min-height: 100%; background: var(--primary-background-color); }
      .bar {
        display: flex; align-items: center; gap: 8px; height: var(--header-height, 56px); padding: 0 8px;
        background: var(--app-header-background-color); color: var(--app-header-text-color, var(--primary-text-color));
        border-bottom: var(--app-header-border-bottom, none); font-size: 20px;
      }
      .content { max-width: 1120px; margin: 0 auto; padding: 16px; }
    `;
    this._menu = document.createElement("ha-menu-button");
    const bar = el("div", "bar");
    bar.append(this._menu, el("span", "", "Kilowattlas"));
    const content = el("div", "content");
    this._card = document.createElement("kilowattlas-status-card");
    content.append(this._card);
    this.shadowRoot.append(style, bar, content);
  }

  set hass(hass) {
    this._menu.hass = hass;
    this._card.hass = hass;
  }

  set narrow(narrow) {
    this._menu.narrow = narrow;
  }
}

if (!customElements.get("kilowattlas-status-card")) {
  customElements.define("kilowattlas-status-card", KilowattlasStatusCard);
}
if (!customElements.get("kilowattlas-panel")) {
  customElements.define("kilowattlas-panel", KilowattlasPanel);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "kilowattlas-status-card")) {
  window.customCards.push({
    type: "kilowattlas-status-card",
    name: "Kilowattlas",
    description: "Sharing status of the Kilowattlas integration.",
  });
}
