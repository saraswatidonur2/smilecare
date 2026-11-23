/* SmileCare booking widget. Add to any website with ONE line:
   <script src="https://YOUR-APP-URL/widget.js" data-color="#0d9488" data-clinic="SmileCare"></script> */
(function () {
  var s = document.currentScript;
  var base = new URL(s.src).origin;
  var color = s.getAttribute("data-color") || "#0d9488";
  var clinic = s.getAttribute("data-clinic") || "SmileCare";

  var css = document.createElement("style");
  css.textContent =
    "#sc-btn{position:fixed;right:20px;bottom:20px;z-index:99999;padding:14px 18px;border:0;border-radius:30px;color:#fff;font:600 15px sans-serif;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25)}" +
    "#sc-panel{position:fixed;right:20px;bottom:80px;width:400px;height:600px;max-height:80vh;z-index:99999;display:none;flex-direction:column;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.3);font-family:sans-serif}" +
    "#sc-bar{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;color:#fff;font-weight:600}" +
    "#sc-x{background:none;border:0;color:#fff;font-size:20px;cursor:pointer}" +
    "#sc-panel iframe{border:0;flex:1;width:100%}" +
    "@media(max-width:500px){#sc-panel{right:0;bottom:0;width:100%;height:100%;max-height:100%;border-radius:0}}";
  document.head.appendChild(css);

  var btn = document.createElement("button");
  btn.id = "sc-btn"; btn.textContent = "Book appointment"; btn.style.background = color;

  var panel = document.createElement("div"); panel.id = "sc-panel";
  var bar = document.createElement("div"); bar.id = "sc-bar"; bar.style.background = color;
  var title = document.createElement("span"); title.textContent = clinic;
  var x = document.createElement("button"); x.id = "sc-x"; x.textContent = "\u00d7"; x.setAttribute("aria-label", "Close");
  bar.append(title, x);
  var frame = document.createElement("iframe"); frame.title = clinic + " booking";
  panel.append(bar, frame);

  function toggle(open) {
    if (open && !frame.src) {
      frame.src = base + "/?embed=1&color=" + encodeURIComponent(color) + "&clinic=" + encodeURIComponent(clinic);
    }
    panel.style.display = open ? "flex" : "none";
  }
  btn.onclick = function () { toggle(panel.style.display !== "flex"); };
  x.onclick = function () { toggle(false); };
  document.body.append(panel, btn);
})();
