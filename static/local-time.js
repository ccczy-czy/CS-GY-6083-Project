(function () {
  "use strict";

  /**
   * @param {string} iso
   * @returns {string}
   */
  function formatLocal(iso) {
    var d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return iso;
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(d);
  }

  function upgrade() {
    var nodes = document.querySelectorAll("time.local-datetime[datetime]");
    for (var i = 0; i < nodes.length; i += 1) {
      var el = nodes[i];
      var iso = el.getAttribute("datetime");
      if (!iso) {
        continue;
      }
      el.textContent = formatLocal(iso);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", upgrade);
  } else {
    upgrade();
  }
})();
