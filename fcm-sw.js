/* Service worker di PROVA per Firebase (Fase C). Non e' quello del sito. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });


// Cronologia sul dispositivo: la campanella del sito la legge dalla stessa cache che usava sw.js.
// Gli avvisi che arrivano nello stesso istante si salvano uno dopo l'altro: prima leggevano tutti lo stesso elenco e l'ultimo a scrivere cancellava gli altri.
var histQ = Promise.resolve();
function histSave(title, body, link, tag) {
  var job = histQ.then(function () { return histSaveOne(title, body, link, tag); });
  histQ = job.catch(function () {});
  return job;
}
// Modo «both»: lo stesso avviso arriva due volte (invio diretto + argomento) con lo stesso «tag»: in campanella resta UNA riga sola.
// Il secondo arrivo si annota nella riga gia' salvata (campo arr, letto da avvisi-log.html). Vale solo per avvisi con tag, entro 6 ore.
var TAG_FINESTRA = 6 * 3600 * 1000;
function histSaveOne(title, body, link, tag) {
  var t = Date.now();
  var item = { id: "|" + title + "|" + body + "|" + t, t: t, title: title, body: body, url: /^https?:/.test(link || "") ? link : "" };
  if (tag) { item.tag = tag; item.arr = [t]; }
  return caches.open("vgc-hist").then(function (c) {
    return c.match("hist.json").then(function (r) { return r ? r.json().catch(function () { return []; }) : []; }).then(function (a) {
      if (!Array.isArray(a)) a = [];
      var gia = tag ? a.filter(function (x) { return x && x.tag === tag && Math.abs(t - (x.t || 0)) < TAG_FINESTRA; })[0] : null;
      if (gia) {
        gia.arr = (Array.isArray(gia.arr) ? gia.arr : [gia.t]).concat([t]).slice(-5);
        return c.put("hist.json", new Response(JSON.stringify(a), { headers: { "Content-Type": "application/json" } }));
      }
      a.push(item);
      a.sort(function (p, q) { return q.t - p.t; });
      return c.put("hist.json", new Response(JSON.stringify(a.slice(0, 60)), { headers: { "Content-Type": "application/json" } }));
    });
  }).then(function () {
    return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (cs) {
      cs.forEach(function (w) { w.postMessage({ vgcHist: 1 }); });
    });
  }).catch(function () {});
}

self.addEventListener("push", function (e) {
  var raw = "", j = {};
  try { raw = e.data ? e.data.text() : ""; } catch (x) {}
  try { j = raw ? JSON.parse(raw) : {}; } catch (x) { j = {}; }
  var n0 = j.notification || {}, d0 = j.data || {};
  var voce = { t: new Date().toISOString(), raw: raw.slice(0, 300), title: String(n0.title || d0.title || "").slice(0, 200), body: String(n0.body || d0.body || "").slice(0, 300) };
  var logP = caches.open("fcm-log").then(function (c) {
    return c.put("/fcm-log/" + Date.now() + "-" + Math.floor(Math.random() * 1000), new Response(JSON.stringify(voce))).then(function () {
      return c.keys();
    }).then(function (ks) {
      var extra = ks.length - 200;
      return extra > 0 ? Promise.all(ks.slice(0, extra).map(function (k) { return c.delete(k); })) : null;
    });
  }).catch(function () {});
  try { j = raw ? JSON.parse(raw) : {}; } catch (x) { j = {}; }
  var n = j.notification || {}, d = j.data || {};
  var title = n.title || d.title || "rAKings VGC";
  var body = n.body || d.body || (!n.title && !d.title ? raw.slice(0, 200) : "");
  var link = (j.fcmOptions && j.fcmOptions.link) || n.click_action || d.link || d.url || "./";
  e.waitUntil(Promise.all([logP, histSave(title, body, link, d.tag || ""), self.registration.showNotification(title, {
    body: body,
    icon: n.icon || d.icon || "icon-192.png",
    badge: "badge-96.png",
    data: { link: link },
    tag: d.tag || undefined
  })]));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var link = (e.notification.data && e.notification.data.link) || "./";
  var base = new URL("./", self.location.href);        // radice del sito
  var url = new URL(link, base).href;
  var inSite = url.indexOf(base.href) === 0;
  var go = { url: url, id: String(Date.now()) + Math.random() };
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    var c = null;
    if (inSite) for (var i = 0; i < list.length; i++) { if (list[i].url.indexOf(base.href) === 0 && "focus" in list[i]) { c = list[i]; break; } }
    if (!c) return self.clients.openWindow(url);          // sito chiuso o link esterno: si apre normalmente
    // sito gia' aperto: lo porto in primo piano e gli dico dove andare (niente seconda finestra)
    try { new BroadcastChannel("vgc-nav").postMessage(go); } catch (x) {}
    return c.focus().then(function (w) { try { (w || c).postMessage({ vgcGo: url, id: go.id }); } catch (x) {} }, function () {});
  }));
});
