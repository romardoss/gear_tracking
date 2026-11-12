// POC: захардкоджені дані. У реальній версії тут буде база.
const svg = (bg, body) => 'data:image/svg+xml;utf8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="400" height="300" fill="${bg}"/>${body}</svg>`);

const ITEMS = [
  { id: 1, name: "Мотузка динамічна 60 м", holder: "Олена Коваленко",
    photo: svg("#dbeafe", `<path d="M60 220 C120 60 180 260 240 120 S340 80 350 160" fill="none" stroke="#d97706" stroke-width="18" stroke-linecap="round"/>
      <path d="M60 220 C120 60 180 260 240 120 S340 80 350 160" fill="none" stroke="#fff" stroke-width="4" stroke-dasharray="10 14" stroke-linecap="round"/>`) },
  { id: 2, name: "Страхувальна система (обв'язка)", holder: "Андрій Мельник",
    photo: svg("#dcfce7", `<g fill="none" stroke="#1d4ed8" stroke-width="16" stroke-linecap="round">
      <ellipse cx="200" cy="110" rx="70" ry="22"/><path d="M135 120 L160 230 M265 120 L240 230"/><path d="M160 230 Q200 260 240 230"/></g>
      <rect x="185" y="95" width="30" height="30" rx="6" fill="#facc15"/>`) },
  { id: 3, name: "Шолом альпіністський", holder: "Марія Шевчук",
    photo: svg("#fee2e2", `<path d="M90 190 A110 100 0 0 1 310 190 Z" fill="#ef4444"/>
      <rect x="80" y="190" width="240" height="16" rx="8" fill="#991b1b"/>
      <g fill="#fff"><rect x="150" y="120" width="14" height="30" rx="7"/><rect x="193" y="105" width="14" height="30" rx="7"/><rect x="236" y="120" width="14" height="30" rx="7"/></g>`) },
];
