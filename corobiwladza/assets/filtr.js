// Filtr „zgodne/sporne”. Bez skryptu strona pokazuje wszystkie uchwały.
(function () {
  var box = document.querySelector(".filter");
  if (!box) return;
  box.hidden = false;
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card[data-zgodna]"));
  var buttons = Array.prototype.slice.call(box.querySelectorAll("button[data-f]"));
  var out = document.getElementById("f-count");
  function apply(f) {
    var shown = 0;
    cards.forEach(function (c) {
      var ok = f === "all" || c.getAttribute("data-zgodna") === f;
      c.hidden = !ok;
      if (ok) shown++;
    });
    Array.prototype.forEach.call(document.querySelectorAll("section.theme"), function (sec) {
      sec.hidden = !sec.querySelector(".card:not([hidden])");
    });
    buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-f") === f)); });
    if (out) out.textContent = "Widocznych uchwał: " + shown + " z " + cards.length;
  }
  buttons.forEach(function (b) {
    b.addEventListener("click", function () { apply(b.getAttribute("data-f")); });
  });
})();
