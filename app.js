const state = {
  movies: [],
  comments: [],
  votes: {},
  voted: [],
  filter: "all",
  exactList: "all",
  franchise: null,
  query: "",
  activeMovie: null,
  featuredIndex: 0,
  featuredRenderToken: 0,
  busy: false,
  supabase: null,
  supabaseConfigured: false,
  user: null,
  authSubscription: null,
  nominations: [],
  leaderboard: [],
  ratings: {},
  myRatings: {},
  catalogVersion: null,
  catalogPoll: null
};

const featuredPosterPromises = new Map();
const UNWATCHED_LISTS = [
  "PRÓXIMAS SESSÕES",
  "STREAMING - DISPONÍVEL",
  "STREAMING - EM BREVE",
  "FILMES A ASSISTIR"
];

const AWARD_CATEGORIES = [
  "FILME NACIONAL", "FILME INTERNACIONAL", "ATOR PRINCIPAL", "ATRIZ PRINCIPAL",
  "ATOR COADJUVANTE", "ATRIZ COADJUVANTE", "DIREÇÃO", "ROTEIRO",
  "FIGURINO E MAQUIAGEM", "DESIGN DE PRODUÇÃO", "EFEITOS PRÁTICOS",
  "EFEITOS DIGITAIS", "INVERSÃO NARRATIVA", "SOLUÇÃO NARRATIVA",
  "ARCO DE PROTAGOSNSTA", "ARCO DE ANTAGONISTA", "LACRAÇÃO PONTUAL",
  "LACRAÇÃO GERAL", "PRÊMIO DESONORÁRIO", "FORA DA PREMIAÇÃO"
];

const coreLists = new Set([
  "PRÓXIMAS SESSÕES",
  "STREAMING - DISPONÍVEL",
  "STREAMING - EM BREVE",
  "FILMES A ASSISTIR",
  "ASSISTIDOS — PENDENTE DE CATEGORIZAÇÃO",
  "FORA DA PREMIAÇÃO"
]);

const filters = [
  { id: "all", label: "Catálogo completo", test: function () { return true; } },
  { id: "sessions", label: "Próximas sessões", test: function (movie) { return movie.list === "PRÓXIMAS SESSÕES"; } },
  { id: "streaming", label: "No streaming", test: function (movie) { return movie.list === "STREAMING - DISPONÍVEL"; } },
  { id: "soon", label: "Em breve", test: function (movie) { return movie.list === "STREAMING - EM BREVE"; } },
  { id: "watchlist", label: "A assistir", test: function (movie) { return movie.list === "FILMES A ASSISTIR"; } },
  { id: "most-wanted", label: "Mais pedidos", test: function (movie) { return !isWatched(movie) && interestCount(movie) > 0; } },
  { id: "most-hated", label: "Mais odiados", test: function (movie) { return isWatched(movie) && ratingFor(movie).count > 0; } },
  { id: "alhometro", label: "Alhômetro", test: function (movie) { return isWatched(movie) && ratingFor(movie).count > 0; } },
  { id: "watched", label: "Assistidos", test: isWatched },
  { id: "pending-award", label: "Pendentes de indicação", test: function (movie) { return movie.list === "ASSISTIDOS — PENDENTE DE CATEGORIZAÇÃO"; } },
  { id: "awards", label: "Prêmio Alho", test: function (movie) { return !coreLists.has(movie.list); } }
];

const $ = function (selector) { return document.querySelector(selector); };
const $$ = function (selector) { return Array.from(document.querySelectorAll(selector)); };
const esc = function (value) {
  return String(value == null ? "" : value).replace(/[&<>'"]/g, function (char) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char];
  });
};

function legacyIdentity() {
  var id = localStorage.getItem("oscar-alho-user-id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("oscar-alho-user-id", id);
  }
  return id;
}

function notice(message) {
  var toast = $("#toast");
  toast.querySelector("span").textContent = message;
  toast.hidden = false;
}

function statusLabel(movie) {
  if (movie.list === "PRÓXIMAS SESSÕES") return movie.sessionDate ? "Sessão marcada" : "Data em definição";
  if (movie.list === "STREAMING - DISPONÍVEL") return "Disponível agora";
  if (movie.list === "STREAMING - EM BREVE") return "Chega em breve";
  if (movie.list === "FILMES A ASSISTIR") return "Na lista do clube";
  if (movie.list.startsWith("ASSISTIDOS")) return "Já assistido";
  return movie.list;
}

function normalizeMovieTitle(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function movieKey(movie) {
  if (!movie) return "";
  if (movie.canonicalKey) return movie.canonicalKey;
  var imdbMatch = String(movie.imdbUrl || "").match(/\/title\/(tt\d+)/i);
  if (imdbMatch) return "imdb:" + imdbMatch[1].toLowerCase();
  return "title:" + (normalizeMovieTitle(movie.imdbTitle || movie.title) || String(movie.id || "").toLowerCase());
}

function movieGroup(movie) {
  var key = movieKey(movie);
  return state.movies.filter(function (item) { return movieKey(item) === key; });
}

function uniqueMovies(movies) {
  var seen = new Set();
  return movies.filter(function (movie) {
    var key = movieKey(movie);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function isBrazilian(movie) {
  return movieGroup(movie).some(function (item) {
    var labels = (item.labels || []).join(" ");
    var text = [item.list, labels, item.description].filter(Boolean).join("\n")
      .normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
    return item.list === "FILME NACIONAL" || /(^|\n)(PAIS|NACIONALIDADE|ORIGEM):\s*BRASIL\b/.test(text) || /\b(BRASILEIRO|BRASILEIRA|BOSTIL)\b/.test(labels.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toUpperCase());
  });
}

function interestCount(movie) {
  return Number(state.votes[typeof movie === "string" ? movie : movieKey(movie)] || 0);
}

function ratingFor(movie) {
  return state.ratings[typeof movie === "string" ? movie : movieKey(movie)] || { average: null, count: 0 };
}

function isWatched(movie) {
  var list = String(movie.list || "");
  return list.startsWith("ASSISTIDOS") || ![
    "PRÓXIMAS SESSÕES",
    "STREAMING - DISPONÍVEL",
    "STREAMING - EM BREVE",
    "FILMES A ASSISTIR"
  ].includes(list);
}

function watchState(movie) {
  if (isWatched(movie)) return { label: "Assistido pelo clube", className: "watched" };
  if (movie.list === "PRÓXIMAS SESSÕES") return { label: "Sessão programada", className: "scheduled" };
  if (movie.list === "STREAMING - DISPONÍVEL") return { label: "Ainda não assistido", className: "unwatched" };
  if (movie.list === "STREAMING - EM BREVE") return { label: "Aguardando lançamento", className: "unwatched" };
  return { label: "Na lista para assistir", className: "unwatched" };
}
var franchiseTitles = {
  "Saga 28 Days Later": ["Extermínio", "Extermínio 2", "Extermínio: A Evolução", "Extermínio: O Templo dos Ossos"],
  "Saga Pânico": ["Pânico", "Pânico 2", "Pânico 3", "Pânico 4", "Pânico (2022)", "Pânico VI", "Pânico 7"],
  "Jogos Vorazes": ["Jogos Vorazes", "Em Chamas", "A Esperança — Parte 1", "A Esperança — O Final", "A Cantiga dos Pássaros e das Serpentes", "Amanhecer na Colheita"],
  "Scary Movie": ["Todo Mundo em Pânico", "Todo Mundo em Pânico 2", "Todo Mundo em Pânico 3", "Todo Mundo em Pânico 4", "Todo Mundo em Pânico 5", "Todo Mundo em Pânico 6"],
  "Sobrenatural": ["Sobrenatural", "Sobrenatural: Capítulo 2", "Sobrenatural: A Origem", "Sobrenatural: A Última Chave", "Sobrenatural: A Porta Vermelha", "Sobrenatural: Agora Entre Nós"],
  "Twisted Childhood Universe": ["Ursinho Pooh: Sangue e Mel", "Ursinho Pooh: Sangue e Mel 2", "Peter Pan: Pesadelo na Terra do Nunca", "Bambi: A Vingança", "Pinóquio: Unstrung", "Poohniverso: Monstros Unidos"],
  "Terrifier": ["Terrifier", "Terrifier 2", "Terrifier 3", "Terrifier 4"],
  "Os Estranhos": ["Os Estranhos: Capítulo 1", "Os Estranhos: Capítulo 2", "Os Estranhos: Capítulo Final"],
  "Se Eu Fosse Você": ["Se Eu Fosse Você", "Se Eu Fosse Você 2", "Se Eu Fosse Você 3"],
  "Super Troopers": ["Super Tiras", "Super Tiras 2", "Super Tiras 3"],
  "Toy Story": ["Toy Story", "Toy Story 2", "Toy Story 3", "Toy Story 4", "Toy Story 5"],
  "Mortal Kombat": ["Mortal Kombat", "Mortal Kombat 2"],
  "Greenland": ["Destruição Final", "Destruição Final 2"],
  "Noite Infeliz": ["Noite Infeliz", "Noite Infeliz 2"],
  "Casamento Sangrento": ["Casamento Sangrento", "A Viúva"],
  "A Queda": ["A Queda", "A Queda 2"],
  "Era Uma Vez em... Hollywood": ["Era Uma Vez em... Hollywood", "As Aventuras de Cliff Booth"]
};
function sessionParts(value) {
  if (!value) return { day: "—", month: "DATA", time: "A definir" };
  var match = value.match(/(\d{2})\/(\d{2})\/\d{4},?\s*(.*)/);
  if (!match) return { day: "—", month: "DATA", time: value };
  var months = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
  return { day: match[1], month: months[Number(match[2]) - 1], time: match[3] || "A definir" };
}

function preloadFeaturedPoster(src) {
  if (!src) return Promise.resolve();
  if (featuredPosterPromises.has(src)) return featuredPosterPromises.get(src);

  var promise = new Promise(function (resolve) {
    var image = new Image();
    var settled = false;
    var finish = async function () {
      if (settled) return;
      settled = true;
      try {
        if (image.decode) await image.decode();
      } catch (_error) {
        // A failed decode still lets the real image element handle its fallback.
      }
      resolve();
    };
    image.onload = finish;
    image.onerror = finish;
    image.src = src;
    if (image.complete) finish();
  });

  featuredPosterPromises.set(src, promise);
  return promise;
}

async function renderFeaturedSession(sessions, index) {
  if (!sessions.length) return;
  var nextIndex = (index + sessions.length) % sessions.length;
  var featured = sessions[nextIndex];
  var renderToken = ++state.featuredRenderToken;
  state.featuredIndex = nextIndex;
  var controls = $("#featured-carousel-controls");
  var buttons = controls ? Array.from(controls.querySelectorAll("button")) : [];
  if (controls) controls.setAttribute("aria-busy", "true");
  buttons.forEach(function (button) { button.disabled = true; });

  await preloadFeaturedPoster(featured.poster);
  if (renderToken !== state.featuredRenderToken) return;

  $("#featured-title").textContent = featured.title;
  $("#featured-status").textContent = featured.sessionStatus || "Programação do clube";
  $("#featured-poster").src = featured.poster;
  $("#featured-poster").alt = "Pôster de " + featured.title;
  $("#featured-synopsis").textContent = featured.synopsis || "Abra a ficha para ver as informações completas do card no Trello.";
  $("#featured-meta").innerHTML = [
    featured.sessionDate || "Data em definição",
    featured.duration || "Duração a definir",
    featured.streaming || "Plataforma a confirmar"
  ].map(function (item) { return "<span>" + esc(item) + "</span>"; }).join("");
  $("#featured-details").onclick = function () { openMovie(featured.id); };
  var key = (featured.sessionDate || featured.id).replace(/\D/g, "") || featured.id;
  $("#rsvp-button").onclick = function () { rsvp(featured, key); };
  $("#featured-position").textContent = (nextIndex + 1) + " de " + sessions.length;
  if (controls) controls.removeAttribute("aria-busy");
  buttons.forEach(function (button) { button.disabled = false; });
}
function franchiseKey(value) {
  if (!value || /^(—|-|filme original)$/i.test(value.trim())) return null;
  return value
    .replace(/\s*\((?:filme|parte)\s+\d+\s+de\s+\d+\)\s*$/i, "")
    .replace(/\s*\((?:filme|parte)[^)]+\)\s*$/i, "")
    .trim();
}

function franchisePosition(value) {
  var match = String(value || "").match(/(?:filme|parte)\s+(\d+)\s+de\s+(\d+)/i);
  return match ? { current: Number(match[1]), total: Number(match[2]) } : null;
}

function franchiseGroups() {
  var map = new Map();
  state.movies.forEach(function (movie) {
    var key = franchiseKey(movie.franchise);
    if (!key) return;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(movie);
  });
  return Array.from(map.entries())
    .map(function (entry) {
      entry[1].sort(function (a, b) {
        var pa = franchisePosition(a.franchise);
        var pb = franchisePosition(b.franchise);
        return (pa ? pa.current : 999) - (pb ? pb.current : 999) || a.title.localeCompare(b.title, "pt-BR");
      });
      var total = entry[1].reduce(function (highest, movie) {
        var position = franchisePosition(movie.franchise);
        return Math.max(highest, position ? position.total : 0);
      }, entry[1].length);
      return { name: entry[0], movies: entry[1], total: total };
    })
    .filter(function (group) { return group.total > 1 || group.movies.length > 1; })
    .sort(function (a, b) { return b.total - a.total || a.name.localeCompare(b.name, "pt-BR"); });
}
function renderHeaderAndSchedule(catalog) {
  var sessions = state.movies.filter(function (movie) { return movie.list === "PRÓXIMAS SESSÕES"; });
  $("#updated-at").textContent = "Catálogo atualizado em " + new Date(catalog.updatedAt).toLocaleDateString("pt-BR");
  sessions.forEach(function (movie) { preloadFeaturedPoster(movie.poster); });
  var initialIndex = sessions.findIndex(function (movie) { return Boolean(movie.sessionDate); });
  renderFeaturedSession(sessions, initialIndex >= 0 ? initialIndex : 0);
  var controls = $("#featured-carousel-controls");
  controls.hidden = sessions.length < 2;
  if (sessions.length > 1) {
    $("#featured-prev").onclick = function () { renderFeaturedSession(sessions, state.featuredIndex - 1); };
    $("#featured-next").onclick = function () { renderFeaturedSession(sessions, state.featuredIndex + 1); };
  }

  $("#schedule-grid").innerHTML = sessions.map(function (movie) {
    var date = sessionParts(movie.sessionDate);
    return '<article class="schedule-card">' +
      '<img src="' + esc(movie.poster) + '" alt="Pôster de ' + esc(movie.title) + '" />' +
      '<div class="schedule-copy"><span class="date-chip">' + esc(date.day + " " + date.month + " · " + date.time) + '</span>' +
      '<h3>' + esc(movie.title) + '</h3><p>' + esc(movie.sessionProgramming || movie.streaming || "Plataforma a definir") +
      (movie.duration ? " · " + esc(movie.duration) : "") + '</p>' +
      '<div class="session-live-links"><a href="https://kick.com/panneelinha" target="_blank" rel="noreferrer">Assistir na Kick</a>' +
      '<a href="https://discord.gg/zdxTPpuvaq" target="_blank" rel="noreferrer">Entrar no Discord</a></div></div>' +
      '<button class="text-button" data-open="' + esc(movie.id) + '">Abrir filme</button></article>';
  }).join("");
  wireMovieOpeners();
}

function renderFranchises() {
  var groups = franchiseGroups().slice(0, 12);
  $("#franchise-rail").innerHTML = groups.map(function (group) {
    var cover = group.movies[0];
    var countLabel = group.movies.length === group.total
      ? group.total + " filmes"
      : group.movies.length + " no catálogo · " + group.total + " na franquia";
    return '<button class="franchise-card" data-franchise="' + esc(group.name) + '" type="button">' +
      '<img src="' + esc(cover.poster) + '" alt="" />' +
      '<div><strong>' + esc(group.name) + '</strong><span>' + esc(countLabel) + '</span></div></button>';
  }).join("");
  $$('[data-franchise]').forEach(function (button) {
    button.onclick = function () {
      state.franchise = button.dataset.franchise;
      state.filter = "all";
      state.exactList = "all";
      $("#list-filter").value = "all";
      renderFilters();
      renderMovies();
      location.hash = "catalogo";
    };
  });
}
function renderFilters() {
  var clearFranchise = state.franchise
    ? '<button data-clear-franchise="1" class="active">Franquia: ' + esc(state.franchise) + '<span>×</span></button>'
    : "";
  $("#filter-row").innerHTML = clearFranchise + filters.map(function (filter) {
    var count = state.movies.filter(filter.test).length;
    return '<button data-filter="' + filter.id + '" class="' + (filter.id === state.filter && !state.franchise ? "active" : "") + '">' +
      esc(filter.label) + '<span>' + count + '</span></button>';
  }).join("");

  var clear = $("[data-clear-franchise]");
  if (clear) clear.onclick = function () { state.franchise = null; renderFilters(); renderMovies(); };
  $$("[data-filter]").forEach(function (button) {
    button.onclick = function () {
      state.filter = button.dataset.filter;
      state.exactList = "all";
      state.franchise = null;
      $("#list-filter").value = "all";
      renderFilters();
      renderMovies();
    };
  });

  var lists = Array.from(new Set(state.movies.map(function (movie) { return movie.list; }))).sort(function (a, b) {
    return a.localeCompare(b, "pt-BR");
  });
  $("#list-filter").innerHTML = '<option value="all">Todas as listas</option>' + lists.map(function (list) {
    return '<option value="' + esc(list) + '">' + esc(list) + '</option>';
  }).join("");
  $("#list-filter").value = state.exactList;
}

function visibleMovies() {
  var active = filters.find(function (item) { return item.id === state.filter; }) || filters[0];
  var query = state.query.trim().toLocaleLowerCase("pt-BR");
  var movies = state.movies
    .filter(active.test)
    .filter(function (movie) { return state.exactList === "all" || movie.list === state.exactList; })
    .filter(function (movie) { return !state.franchise || franchiseKey(movie.franchise) === state.franchise; })
    .filter(function (movie) {
      if (!query) return true;
      return [movie.title, movie.streaming, movie.list, movie.franchise, movie.genres]
        .concat(movie.labels || [])
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("pt-BR")
        .includes(query);
    })
    .sort(function (a, b) {
      if (state.filter === "most-wanted") {
        return interestCount(b) - interestCount(a) || a.title.localeCompare(b.title, "pt-BR");
      }
      if (state.filter === "most-hated") {
        var hatedA = ratingFor(a);
        var hatedB = ratingFor(b);
        return Number(hatedA.average || 0) - Number(hatedB.average || 0) || hatedB.count - hatedA.count || a.title.localeCompare(b.title, "pt-BR");
      }
      if (state.filter === "alhometro") {
        var ratingA = ratingFor(a);
        var ratingB = ratingFor(b);
        return Number(ratingB.average || 0) - Number(ratingA.average || 0) || ratingB.count - ratingA.count || a.title.localeCompare(b.title, "pt-BR");
      }
      return a.listOrder - b.listOrder || a.title.localeCompare(b.title, "pt-BR");
    });
  return ["most-wanted", "most-hated", "alhometro"].includes(state.filter) ? uniqueMovies(movies) : movies;
}

function renderMostWanted() {
  var rail = $("#most-wanted-rail");
  if (!rail) return;
  var movies = uniqueMovies(state.movies
    .filter(function (movie) { return !isWatched(movie) && interestCount(movie) > 0; }))
    .sort(function (a, b) { return interestCount(b) - interestCount(a) || a.title.localeCompare(b.title, "pt-BR"); })
    .slice(0, 10);

  $("#most-wanted-empty").hidden = movies.length > 0;
  rail.innerHTML = movies.map(function (movie, index) {
    var count = interestCount(movie);
    return '<article class="wanted-card">' +
      '<button type="button" data-open="' + esc(movie.id) + '" aria-label="Abrir ' + esc(movie.title) + '">' +
      '<span class="wanted-position">' + (index + 1) + '</span><img src="' + esc(movie.poster) + '" alt="" loading="lazy" />' +
      '<span class="wanted-count">🍿 ' + count + '</span></button>' +
      '<div><h3>' + esc(movie.title) + '</h3><p>' + count + (count === 1 ? ' pessoa quer assistir' : ' pessoas querem assistir') + '</p></div>' +
      '</article>';
  }).join("");
  wireMovieOpeners();
}

function renderMostHated() {
  var rail = $("#most-hated-rail");
  if (!rail) return;
  var movies = uniqueMovies(state.movies.filter(function (movie) {
    return isWatched(movie) && ratingFor(movie).count > 0;
  })).sort(function (a, b) {
    var ratingA = ratingFor(a);
    var ratingB = ratingFor(b);
    return Number(ratingA.average || 0) - Number(ratingB.average || 0) || ratingB.count - ratingA.count || a.title.localeCompare(b.title, "pt-BR");
  }).slice(0, 10);

  $("#most-hated-empty").hidden = movies.length > 0;
  rail.innerHTML = movies.map(function (movie, index) {
    var rating = ratingFor(movie);
    return '<article class="wanted-card hated-card">' +
      '<button type="button" data-open="' + esc(movie.id) + '" aria-label="Abrir ' + esc(movie.title) + '">' +
      '<span class="wanted-position">' + (index + 1) + '</span><img src="' + esc(movie.poster) + '" alt="" loading="lazy" />' +
      '<span class="wanted-count">🧄 ' + esc(Number(rating.average).toFixed(1).replace(".", ",")) + '/10</span></button>' +
      '<div><h3>' + esc(movie.title) + '</h3><p>' + rating.count + (rating.count === 1 ? ' avaliação' : ' avaliações') + '</p></div>' +
      '</article>';
  }).join("");
  wireMovieOpeners();
}

function renderMovies() {
  var movies = visibleMovies();
  $("#result-count").textContent = movies.length;
  $("#result-label").textContent = movies.length === 1 ? "filme encontrado" : "filmes encontrados";
  $("#empty").hidden = movies.length !== 0;
  $("#movie-grid").innerHTML = movies.map(function (movie, index) {
    var key = movieKey(movie);
    var count = interestCount(movie);
    var rating = ratingFor(movie);
    var wants = state.voted.includes(key);
    return '<article class="movie-card"><button class="poster-button" data-open="' + esc(movie.id) + '" aria-label="Abrir ' + esc(movie.title) + '">' +
      '<img src="' + esc(movie.poster) + '" alt="Pôster de ' + esc(movie.title) + '" loading="' + (index < 12 ? "eager" : "lazy") + '" />' +
      '<span class="card-status">' + esc(statusLabel(movie)) + '</span>' +
      (isBrazilian(movie) ? '<span class="card-bostil" title="Filme brasileiro">BOSTIL</span>' : '') +
      (rating.count ? '<span class="card-alho" title="Alhômetro do clube">🧄 ' + esc(Number(rating.average).toFixed(1).replace(".", ",")) + '</span>' : '') +
      (movie.imdb ? '<span class="card-rating">IMDb ' + esc(movie.imdb.replace("/10", "")) + '</span>' : "") +
      '</button><div class="movie-copy"><p>' + esc(movie.franchise || movie.streaming || movie.list) + '</p><h3>' + esc(movie.title) + '</h3>' +
      '<div class="movie-actions"><button data-vote="' + esc(movie.id) + '" class="want-button ' + (wants ? "voted" : "") + '">' +
      (wants ? "✓ Quero assistir" : "🍿 Quero assistir") + ' <span>' + count + '</span></button>' +
      '<button data-comment="' + esc(movie.id) + '">' + (state.user ? "Comentar" : "Ver comentários") + '</button></div></div></article>';
  }).join("");
  wireMovieOpeners();
  $$("[data-vote]").forEach(function (button) { button.onclick = function () { toggleVote(button.dataset.vote); }; });
  renderMostWanted();
  renderMostHated();
}

function wireMovieOpeners() {
  $$("[data-open],[data-comment]").forEach(function (button) {
    button.onclick = function () { openMovie(button.dataset.open || button.dataset.comment); };
  });
}

function metaItem(label, value) {
  return value ? "<div><dt>" + esc(label) + "</dt><dd>" + esc(value) + "</dd></div>" : "";
}

function openMovie(id) {
  var movie = state.movies.find(function (item) { return item.id === id; });
  if (!movie) return;
  state.activeMovie = movie;
  $("#modal-poster").src = movie.poster;
  $("#modal-poster").alt = "Pôster de " + movie.title;
  $("#modal-status").textContent = statusLabel(movie);
  $("#movie-modal-title").textContent = movie.title;
  $("#modal-list").textContent = movie.list;
  $("#modal-original-title").textContent = movie.imdbTitle && movie.imdbTitle !== movie.title ? movie.imdbTitle : "";
  var currentWatchState = watchState(movie);
  $("#modal-chips").innerHTML =
    '<span class="watch-state ' + esc(currentWatchState.className) + '">' + esc(currentWatchState.label) + '</span>' +
    []
      .concat(movie.genres ? movie.genres.split(/[;,]/) : [])
      .concat(movie.labels || [])
      .filter(Boolean)
      .map(function (item) { return "<span>" + esc(item.trim()) + "</span>"; })
      .join("");  $("#modal-meta").innerHTML =
    metaItem("Onde assistir", movie.streaming) +
    metaItem("Data no streaming", movie.streamingDate) +
    metaItem("Duração", movie.duration) +
    metaItem("IMDb", movie.imdb ? movie.imdb + (movie.imdbReviews ? " · " + movie.imdbReviews + " avaliações" : "") : null) +
    metaItem("Estreia", movie.release) +
    metaItem("Sessão", movie.sessionDate) +
    metaItem("Programação", movie.sessionProgramming) +
    metaItem("Status", movie.sessionStatus);
  $("#modal-synopsis").textContent = movie.synopsis || "A sinopse ainda não foi cadastrada nos comentários do card no Trello.";
  $("#modal-description").textContent = movie.description || "Sem descrição adicional no Trello.";
  $("#modal-imdb").hidden = !movie.imdbUrl;
  if (movie.imdbUrl) $("#modal-imdb").href = movie.imdbUrl;
  $("#modal-trailer").hidden = !movie.trailerUrl;
  if (movie.trailerUrl) $("#modal-trailer").href = movie.trailerUrl;
  renderFranchiseSequence(movie);
  renderNomination(movie);
  renderRating(movie);
  updateModalVote();
  renderComments();
  $("#modal").hidden = false;
  document.body.classList.add("movie-details-open");
  document.body.style.overflow = "hidden";
}

function renderFranchiseSequence(movie) {
  var key = franchiseKey(movie.franchise);
  var section = $("#franchise-section");
  if (!key) {
    section.hidden = true;
    return;
  }
  var group = franchiseGroups().find(function (item) { return item.name === key; });
  if (!group) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  $("#modal-franchise-name").textContent = group.name;
  var currentPosition = franchisePosition(movie.franchise);
  $("#modal-franchise-position").textContent = currentPosition
    ? "Filme " + currentPosition.current + " de " + group.total
    : group.movies.length + " de " + group.total + " no catálogo";

  var positioned = new Map();
  var unpositioned = [];
  group.movies.forEach(function (item) {
    var position = franchisePosition(item.franchise);
    if (position) positioned.set(position.current, item);
    else unpositioned.push(item);
  });

  var slots = Array.from({ length: group.total }, function (_unused, index) {
    return { position: index + 1, movie: positioned.get(index + 1) || unpositioned.shift() || null };
  });

  $("#franchise-sequence").innerHTML = slots.map(function (slot) {
    if (!slot.movie) {
      var mappedTitles = franchiseTitles[group.name] || [];
      var mappedTitle = mappedTitles[slot.position - 1];
      return '<div class="franchise-missing">' +
        '<img src="/poster-fallback.png" alt="" />' +
        '<div><strong>' + esc(mappedTitle || ("Filme " + slot.position + " da franquia")) + '</strong>' +
        '<small>Ainda não está cadastrado no catálogo</small></div>' +
        '<span class="watch-state unknown">Status não informado</span></div>';
    }
    var item = slot.movie;
    var itemWatch = watchState(item);
    return '<button type="button" data-franchise-movie="' + esc(item.id) + '" class="' + (item.id === movie.id ? "active" : "") + '">' +
      '<img src="' + esc(item.poster) + '" alt="" />' +
      '<div><strong>' + esc(item.title) + '</strong><small>Filme ' + slot.position + ' de ' + group.total + '</small></div>' +
      '<span class="watch-state ' + esc(itemWatch.className) + '">' + esc(itemWatch.label) + '</span></button>';
  }).join("");

  $$('[data-franchise-movie]').forEach(function (button) {
    button.onclick = function () { openMovie(button.dataset.franchiseMovie); };
  });
}
function renderNomination(movie) {
  var watched = isWatched(movie);
  var openButton = $("#open-nomination");
  var section = $("#nomination-section");
  openButton.hidden = !watched;
  section.hidden = true;
  if (!watched) return;

  var options = AWARD_CATEGORIES.map(function (category) {
    return '<option value="' + esc(category) + '">' + esc(category) + '</option>';
  }).join("");
  $("#nomination-category").innerHTML = '<option value="">Escolha uma categoria</option>' + options;
  var own = state.nominations.filter(function (item) { return item.movie_id === movie.id; });
  $("#nomination-history").textContent = own.length
    ? "Você já indicou este filme em " + own.length + (own.length === 1 ? " categoria." : " categorias.")
    : "Sua primeira indicação deste filme vale 3 pontos.";
}

function renderRanking() {
  var board = $("#ranking-board");
  if (!board) return;
  if (!state.leaderboard.length) {
    board.innerHTML = '<p class="ranking-empty">O ranking começa com a próxima participação. Entre com o Discord e inaugure o placar.</p>';
    return;
  }
  board.innerHTML = state.leaderboard.map(function (member) {
    var avatar = member.avatar_url
      ? '<img src="' + esc(member.avatar_url) + '" alt="" />'
      : '<span class="ranking-avatar">' + esc(String(member.display_name || "?").slice(0, 1).toUpperCase()) + '</span>';
    return '<article class="ranking-row' + (member.is_current_user ? ' current' : '') + '">' +
      '<strong class="ranking-position">' + esc(member.rank_position) + 'º</strong>' + avatar +
      '<div><h3>' + esc(member.display_name) + '</h3><p>' + esc(member.reward_title) + '</p></div>' +
      '<b class="ranking-points">' + esc(member.points) + '<small> pts</small></b></article>';
  }).join("");
}

async function loadLeaderboard() {
  if (!state.supabase) return;
  var result = await state.supabase.rpc("get_club_leaderboard", { result_limit: 50 });
  if (result.error) {
    console.error(result.error);
    return;
  }
  state.leaderboard = (result.data || []).map(function (member) {
    return Object.assign({}, member, { is_current_user: Boolean(state.user && member.user_id === state.user.id) });
  });
  renderRanking();
}function closeModal() {
  $("#modal").hidden = true;
  state.activeMovie = null;
  document.body.classList.remove("movie-details-open");
  document.body.style.overflow = "";
}

function updateModalVote() {
  if (!state.activeMovie) return;
  var key = movieKey(state.activeMovie);
  var active = state.voted.includes(key);
  var count = interestCount(state.activeMovie);
  $("#modal-vote").textContent = active ? "✓ Quero assistir · " + count : "🍿 Quero assistir · " + count;
  $("#modal-vote").classList.toggle("selected", active);
}

function renderRating(movie) {
  var section = $("#alhometro-section");
  if (!section) return;
  var watched = isWatched(movie);
  section.hidden = !watched;
  if (!watched) return;

  var key = movieKey(movie);
  var aggregate = ratingFor(movie);
  var own = Number(state.myRatings[key] || 0);
  $("#alhometro-average").textContent = aggregate.count
    ? Number(aggregate.average).toFixed(1).replace(".", ",") + "/10 · " + aggregate.count + (aggregate.count === 1 ? " avaliação" : " avaliações")
    : "Ainda sem avaliações";
  $("#alhometro-help").textContent = state.user
    ? (own ? "Sua nota atual é " + own + "/10. Escolha outro dente para atualizar." : "Escolha de 1 a 10 dentes de alho. Sua primeira nota vale 2 pontos.")
    : "Entre com o Discord para deixar sua nota.";
  $("#alhometro-scale").innerHTML = Array.from({ length: 10 }, function (_unused, index) {
    var score = index + 1;
    return '<button type="button" data-rating="' + score + '" class="' + (own === score ? 'selected' : '') + '" ' + (!state.user ? 'disabled' : '') + ' aria-label="Dar nota ' + score + ' de 10">' +
      '<span aria-hidden="true">🧄</span><b>' + score + '</b></button>';
  }).join("");
  $$('[data-rating]').forEach(function (button) {
    button.onclick = function () { submitRating(movie.id, Number(button.dataset.rating)); };
  });
}

async function loadRatings() {
  if (!state.supabase) return;
  var aggregateResult = await state.supabase.rpc("get_movie_rating_counts");
  if (!aggregateResult.error) {
    state.ratings = Object.fromEntries((aggregateResult.data || []).map(function (row) {
      return [row.movie_id, { average: Number(row.average_score), count: Number(row.rating_count) }];
    }));
  }
  state.myRatings = {};
  if (state.user) {
    var ownResult = await state.supabase.from("movie_ratings").select("movie_id,rating").eq("user_id", state.user.id);
    if (!ownResult.error) {
      state.myRatings = Object.fromEntries((ownResult.data || []).map(function (row) { return [row.movie_id, Number(row.rating)]; }));
    }
  }
}

async function submitRating(movieId, score) {
  if (state.busy) return;
  if (!state.supabaseConfigured || !state.user || !state.supabase) {
    notice("Entre com o Discord para participar do Alhômetro.");
    return;
  }
  var movie = state.movies.find(function (item) { return item.id === movieId; });
  if (!movie || !isWatched(movie)) {
    notice("O Alhômetro abre depois que o clube assiste ao filme.");
    return;
  }
  state.busy = true;
  try {
    var key = movieKey(movie);
    var wasNew = !state.myRatings[key];
    var result = await state.supabase.from("movie_ratings").upsert({
      user_id: state.user.id,
      movie_id: key,
      rating: score,
      updated_at: new Date().toISOString()
    }, { onConflict: "user_id,movie_id" });
    if (result.error) throw result.error;
    state.myRatings[key] = score;
    await loadRatings();
    renderRating(movie);
    renderMovies();
    await loadLeaderboard();
    notice("Você deu " + score + "/10 dentes de alho para “" + movie.title + "”." + (wasNew ? " +2 pontos!" : " Nota atualizada."));
  } catch (error) {
    console.error(error);
    notice("Não consegui salvar sua nota agora.");
  } finally {
    state.busy = false;
  }
}

function profileName() {
  if (!state.user) return "";
  var meta = state.user.user_metadata || {};
  return meta.full_name || meta.global_name || meta.name || meta.user_name || "Membro do clube";
}

function profileAvatar() {
  if (!state.user) return "";
  var meta = state.user.user_metadata || {};
  return meta.avatar_url || meta.picture || "";
}

function renderAccount() {
  var button = $("#discord-login");
  var formButton = $("#comment-form button[type='submit']");
  var textarea = $("#comment-body");
  var authenticated = Boolean(state.supabaseConfigured && state.user);

  button.classList.toggle("signed-in", authenticated);
  $("#comment-auth-callout").hidden = authenticated;
  formButton.disabled = !authenticated;
  textarea.disabled = !authenticated;
  if (state.activeMovie) { renderNomination(state.activeMovie); renderRating(state.activeMovie); }

  if (authenticated) {
    button.querySelector("span").textContent = profileName() + " · sair";
    textarea.placeholder = "O que você espera — ou teme — deste filme?";
  } else if (state.supabaseConfigured) {
    button.querySelector("span").textContent = "Entrar com Discord";
    textarea.placeholder = "Entre com o Discord para participar da conversa";
  } else {
    button.querySelector("span").textContent = "Discord em configuração";
    textarea.placeholder = "Comentários serão liberados após conectar o Discord";
  }
}
function renderComments() {
  var comments = state.comments.filter(function (item) { return item.movie_id === (state.activeMovie && state.activeMovie.id); });
  $("#comment-count").textContent = comments.length + " " + (comments.length === 1 ? "comentário" : "comentários");
  $("#comment-list").innerHTML = comments.length ? comments.map(function (comment) {
    var author = comment.display_name || comment.author || "Membro do clube";
    var avatar = comment.avatar_url;
    var avatarMarkup = avatar
      ? '<img src="' + esc(avatar) + '" alt="" />'
      : '<span class="comment-avatar">' + esc(author.slice(0, 1).toUpperCase()) + '</span>';
    return '<article>' + avatarMarkup + '<div><p><strong>' + esc(author) + '</strong><time>' +
      new Date(comment.created_at).toLocaleDateString("pt-BR") + '</time></p><blockquote>' + esc(comment.body) + '</blockquote></div></article>';
  }).join("") : '<p class="no-comments">A conversa ainda não começou. Puxe a primeira cadeira.</p>';
}

async function legacyApi(payload) {
  var response = await fetch("/api/club", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error("api");
  return response.json();
}

async function toggleVote(id) {
  if (state.busy) return;
  if (!state.supabaseConfigured || !state.user) {
    notice("Entre com o Discord para marcar o que quer assistir.");
    return;
  }
  var movie = state.movies.find(function (item) { return item.id === id; });
  if (!movie) return;
  var key = movieKey(movie);
  state.busy = true;
  try {
    var active = state.voted.includes(key);
    var count = interestCount(movie);
    if (state.supabaseConfigured) {
      var query = state.supabase.from("movie_votes");
      var result = active
        ? await query.delete().eq("user_id", state.user.id).eq("movie_id", key)
        : await query.insert({ user_id: state.user.id, movie_id: key });
      if (result.error) throw result.error;
      state.voted = active ? state.voted.filter(function (item) { return item !== key; }) : Array.from(new Set(state.voted.concat(key)));
      state.votes[key] = Math.max(0, count + (active ? -1 : 1));
    } else {
      var data = await legacyApi({ action: "toggle_vote", userId: legacyIdentity(), movieId: key });
      state.votes[key] = data.count;
      state.voted = data.active ? Array.from(new Set(state.voted.concat(key))) : state.voted.filter(function (item) { return item !== key; });
      localStorage.setItem("oscar-alho-votes", JSON.stringify(state.voted));
    }
    renderMovies();
    updateModalVote();
    await loadLeaderboard();
    notice(active ? "Filme retirado da sua lista de interesse." : "Interesse registrado. Isso ajuda a priorizar as próximas sessões e valeu 1 ponto.");
  } catch (error) {
    console.error(error);
    notice("Não consegui registrar agora. Tente novamente em instantes.");
  } finally {
    state.busy = false;
  }
}

async function rsvp(movie, key) {
  if (state.busy) return;
  if (!state.supabaseConfigured || !state.user) {
    notice("Entre com o Discord para confirmar presença.");
    return;
  }
  state.busy = true;
  try {
    if (state.supabaseConfigured) {
      var result = await state.supabase.from("session_rsvps").upsert(
        { user_id: state.user.id, session_key: key, movie_id: movie.id, status: "vou" },
        { onConflict: "user_id,session_key" }
      );
      if (result.error) throw result.error;
    } else {
      await legacyApi({ action: "rsvp", userId: legacyIdentity(), sessionKey: key, status: "vou" });
    }
    $("#rsvp-button").textContent = "Presença confirmada";
    $("#rsvp-button").classList.add("selected");
    await loadLeaderboard();
    notice("Presença confirmada para “" + movie.title + "”. Você ganhou 2 pontos.");
  } catch (error) {
    console.error(error);
    notice("Não consegui salvar sua presença agora.");
  } finally {
    state.busy = false;
  }
}

async function loadLegacyInteractions() {
  state.voted = JSON.parse(localStorage.getItem("oscar-alho-votes") || "[]");
  try {
    var response = await fetch("/api/club");
    if (!response.ok) throw new Error("api");
    var data = await response.json();
    state.votes = Object.fromEntries((data.votes || []).map(function (row) { return [row.movie_id, Number(row.count)]; }));
    state.comments = data.comments || [];
  } catch (error) {
    console.error(error);
    notice("O catálogo está disponível; votos e comentários voltarão em instantes.");
  }
  renderMovies();
  renderComments();
}

async function loadSupabaseInteractions() {
  if (!state.supabase) return;
  var countResult = await state.supabase.rpc("get_movie_interest_counts");
  if (countResult.error) countResult = await state.supabase.rpc("get_movie_vote_counts");
  if (!countResult.error) {
    state.votes = Object.fromEntries((countResult.data || []).map(function (row) {
      return [row.movie_id, Number(row.interest_count == null ? row.vote_count : row.interest_count)];
    }));
  }
  await loadRatings();
  var commentsResult = await state.supabase.from("club_comments").select("*").order("created_at", { ascending: false }).limit(300);
  if (!commentsResult.error) state.comments = commentsResult.data || [];
  state.voted = [];
  state.nominations = [];
  if (state.user) {
    var voteResult = await state.supabase.from("movie_votes").select("movie_id").eq("user_id", state.user.id);
    if (!voteResult.error) state.voted = (voteResult.data || []).map(function (row) { return row.movie_id; });
    var nominationResult = await state.supabase.from("movie_nominations").select("movie_id,category").eq("user_id", state.user.id);
    if (!nominationResult.error) state.nominations = nominationResult.data || [];
  }
  await loadLeaderboard();
  renderMovies();
  renderComments();
}

function applyCatalog(catalog) {
  if (!catalog || !Array.isArray(catalog.movies) || !catalog.movies.length) return false;
  var activeId = state.activeMovie && state.activeMovie.id;
  state.movies = catalog.movies.map(function (movie) {
    return Object.assign({}, movie, { canonicalKey: movie.canonicalKey || movieKey(movie) });
  });
  renderHeaderAndSchedule(catalog);
  renderFranchises();
  renderFilters();
  renderMovies();
  if (activeId && !$("#modal").hidden) {
    var stillActive = state.movies.some(function (movie) { return movie.id === activeId; });
    if (stillActive) openMovie(activeId);
    else closeModal();
  }
  return true;
}

async function refreshCatalogFromSupabase(force) {
  if (!state.supabase) return false;
  var statusResult = await state.supabase
    .from("catalog_sync_status")
    .select("last_success_at,movie_count")
    .eq("id", true)
    .maybeSingle();
  if (statusResult.error || !statusResult.data || !statusResult.data.last_success_at) return false;
  var version = statusResult.data.last_success_at;
  if (!force && version === state.catalogVersion) return false;

  var catalogResult = await state.supabase
    .from("catalog_movies")
    .select("payload")
    .eq("active", true)
    .order("position", { ascending: true });
  if (catalogResult.error) throw catalogResult.error;
  var movies = (catalogResult.data || [])
    .map(function (row) { return row.payload; })
    .filter(Boolean);
  if (!movies.length) return false;
  if (applyCatalog({ movies: movies, updatedAt: version })) {
    state.catalogVersion = version;
    return true;
  }
  return false;
}

function startCatalogPolling() {
  if (state.catalogPoll) clearInterval(state.catalogPoll);
  state.catalogPoll = setInterval(function () {
    refreshCatalogFromSupabase(false).catch(function (error) {
      console.warn("Catálogo vivo temporariamente indisponível; mantendo a cópia local.", error);
    });
  }, 10000);
}

async function initSupabase() {
  try {
    var configResponse = await fetch("/api/config");
    var config = configResponse.ok ? await configResponse.json() : {
      supabaseUrl: "https://qchxzzklkcotzohmjujv.supabase.co",
      supabasePublishableKey: "sb_publishable_vgbEtx-BX-W0NfGjk22PFg_eKM8Ourm",
      discordLoginEnabled: true
    };
    var hasSupabase = Boolean(config.supabaseUrl && config.supabasePublishableKey);
    state.supabaseConfigured = Boolean(config.discordLoginEnabled && hasSupabase);
    if (!hasSupabase) {
      renderAccount();
      await loadLegacyInteractions();
      return;
    }
    var module = await import("./vendor/supabase.js");
    state.supabase = module.createClient(config.supabaseUrl, config.supabasePublishableKey, {
      auth: { persistSession: true, detectSessionInUrl: true }
    });
    await refreshCatalogFromSupabase(true);
    startCatalogPolling();
    var sessionResult = await state.supabase.auth.getSession();
    state.user = sessionResult.data.session ? sessionResult.data.session.user : null;
    state.supabase.auth.onAuthStateChange(function (_event, session) {
      state.user = session ? session.user : null;
      renderAccount();
      loadSupabaseInteractions();
    });
    renderAccount();
    await loadSupabaseInteractions();
  } catch (error) {
    console.error(error);
    state.supabaseConfigured = false;
    renderAccount();
    await loadLegacyInteractions();
  }
}
async function loginOrLogout() {
  if (!state.supabaseConfigured || !state.supabase) {
    notice("O login está preparado. Falta conectar o projeto Supabase e ativar o provedor Discord.");
    return;
  }
  if (state.user) {
    await state.supabase.auth.signOut();
    notice("Você saiu da conta do Discord.");
    return;
  }
  var result = await state.supabase.auth.signInWithOAuth({
    provider: "discord",
    options: { redirectTo: window.location.origin }
  });
  if (result.error) notice("Não consegui abrir o login do Discord.");
}

$("#search").addEventListener("input", function (event) {
  state.query = event.target.value;
  renderMovies();
});
$("#list-filter").addEventListener("change", function (event) {
  state.exactList = event.target.value;
  state.filter = "all";
  state.franchise = null;
  renderFilters();
  event.target.value = state.exactList;
  renderMovies();
});
$("#toast").onclick = function () { $("#toast").hidden = true; };
$("#modal-close").onclick = closeModal;
$("#modal").addEventListener("mousedown", function (event) { if (event.target === event.currentTarget) closeModal(); });
document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !$("#modal").hidden) closeModal(); });
$("#modal-vote").onclick = function () { if (state.activeMovie) toggleVote(state.activeMovie.id); };
$("#open-nomination").onclick = function () {
  if (!state.user) { notice("Entre com o Discord para indicar um filme."); return; }
  $("#nomination-section").hidden = false;
  $("#nomination-section").scrollIntoView({ behavior: "smooth", block: "start" });
};
$("#discord-login").onclick = loginOrLogout;
$$('[data-filter-link]').forEach(function (link) {
  link.onclick = function () {
    state.filter = link.dataset.filterLink || "all";
    state.exactList = "all";
    state.franchise = null;
    renderFilters();
    renderMovies();
  };
});

$("#nomination-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  if (!state.activeMovie || state.busy) return;
  if (!state.supabaseConfigured || !state.user || !state.supabase) {
    notice("Entre com o Discord para indicar um filme.");
    return;
  }
  var category = $("#nomination-category").value;
  var justification = $("#nomination-reason").value.trim();
  if (!category || justification.length < 3) return;
  state.busy = true;
  try {
    var result = await state.supabase.from("movie_nominations").upsert({
      user_id: state.user.id,
      movie_id: state.activeMovie.id,
      movie_title: state.activeMovie.title,
      category: category,
      justification: justification
    }, { onConflict: "user_id,movie_id,category" });
    if (result.error) throw result.error;
    var existing = state.nominations.some(function (item) {
      return item.movie_id === state.activeMovie.id && item.category === category;
    });
    if (!existing) state.nominations.push({ movie_id: state.activeMovie.id, category: category });
    $("#nomination-reason").value = "";
    renderNomination(state.activeMovie);
    $("#nomination-section").hidden = false;
    await loadLeaderboard();
    notice(existing ? "Sua justificativa foi atualizada." : "Indicação salva. Ela já entrou na fila da curadoria.");
  } catch (error) {
    console.error(error);
    notice("Não consegui salvar sua indicação agora.");
  } finally {
    state.busy = false;
  }
});
$("#comment-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  if (!state.activeMovie || state.busy) return;
  if (!state.supabaseConfigured || !state.user || !state.supabase) {
    notice("Entre com o Discord para comentar.");
    return;
  }
  var body = $("#comment-body").value.trim();
  if (!body) return;
  state.busy = true;
  try {
    var result = await state.supabase.from("movie_comments").insert({
      user_id: state.user.id,
      movie_id: state.activeMovie.id,
      body: body
    });
    if (result.error) throw result.error;
    state.comments.unshift({
      id: crypto.randomUUID(),
      movie_id: state.activeMovie.id,
      body: body,
      created_at: new Date().toISOString(),
      display_name: profileName(),
      avatar_url: profileAvatar()
    });
    $("#comment-body").value = "";
    renderComments();
    await loadLeaderboard();
    notice("Comentário publicado. Você ganhou 4 pontos.");
  } catch (error) {
    console.error(error);
    notice("Não consegui publicar o comentário agora.");
  } finally {
    state.busy = false;
  }
});
async function hydratePosterPack(catalog) {
  var response = await fetch("./poster-pack-index.json", { cache: "no-store" });
  var manifest = await response.json();
  var parts = await Promise.all(manifest.files.map(function (file) {
    return fetch("./" + file, { cache: "force-cache" }).then(function (item) { return item.arrayBuffer(); });
  }));
  var total = parts.reduce(function (sum, item) { return sum + item.byteLength; }, 0);
  var packed = new Uint8Array(total);
  var cursor = 0;
  parts.forEach(function (item) {
    packed.set(new Uint8Array(item), cursor);
    cursor += item.byteLength;
  });
  var urls = Object.create(null);
  manifest.entries.forEach(function (item) {
    var bytes = packed.slice(item.offset, item.offset + item.length);
    urls[item.id] = URL.createObjectURL(new Blob([bytes], { type: "image/webp" }));
  });
  catalog.movies.forEach(function (movie) {
    movie.poster = urls[movie.id] || "./poster-fallback.webp";
  });
}

fetch("./catalog-index.json", { cache: "no-store" })
  .then(function (response) { return response.json(); })
  .then(async function (manifest) {
    var parts = await Promise.all(manifest.files.map(function (file) {
      return fetch("./" + file, { cache: "no-store" }).then(function (response) { return response.json(); });
    }));
    return { updatedAt: manifest.updatedAt, total: manifest.total, movies: parts.flat() };
  })
  .then(async function (catalog) {
    await hydratePosterPack(catalog);
    applyCatalog(catalog);
    renderAccount();
    renderRanking();
    await initSupabase();
  })
  .catch(function (error) {
    console.error(error);
    if (!state.movies.length) notice("Não consegui abrir o catálogo agora. Atualize a página em instantes.");
  });
