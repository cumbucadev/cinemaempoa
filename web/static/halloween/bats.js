/**
 * BatManager by Corey Snipes <corey@twomile.com>
 *
 * Created from:  JS Bat 2013 - v1.2 - Eric Grange - www.delphitools.info
 */

var BatManager = function () {
  console.log("Bat Manager initiated. Spooky!");

  this.makeBats = function (numBats) {
    for (i = 0; i < numBats; i++) {
      makeBat(i);
    }
  };

  this.markForDeath = function () {
    const bats = document.querySelectorAll('.batjs_bat');
    bats.forEach((bat) => {
      bat.setAttribute('data-deletion', true);
    });
  }

  function makeBat(bat_id) {
    console.log("Bat created");

    var r = Math.random,
      n = 0,
      d = document,
      w = window,
      i = d.createElement("img"),
      z = d.createElement("div"),
      zs = z.style,
      a = w.innerWidth * r(),
      b = w.innerHeight * r();
    zs.position = "fixed";
    zs.left = 0;
    zs.top = 0;
    zs.opacity = 0;
    zs.pointerEvents = 'none';
    z.appendChild(i);
    i.src =
      "data:image/gif;base64,R0lGODlhMAAwAJECAAAAAEJCQv///////yH/C05FVFNDQVBFMi4wAwEAAAAh+QQJAQACACwAAAAAMAAwAAACdpSPqcvtD6NcYNpbr4Z5ewV0UvhRohOe5UE+6cq0carCgpzQuM3ut16zvRBAH+/XKQ6PvaQyCFs+mbnWlEq0FrGi15XZJSmxP8OTRj4DyWY1lKdmV8fyLL3eXOPn6D3f6BcoOEhYaHiImKi4yNjo+AgZKTl5WAAAIfkECQEAAgAsAAAAADAAMAAAAnyUj6nL7Q+jdCDWicF9G1vdeWICao05ciUVpkrZIqjLwCdI16s+5wfck+F8JOBiR/zZZAJk0mAsDp/KIHRKvVqb2KxTu/Vdvt/nGFs2V5Bpta3tBcKp8m5WWL/z5PpbtH/0B/iyNGh4iJiouMjY6PgIGSk5SVlpeYmZqVkAACH5BAkBAAIALAAAAAAwADAAAAJhlI+py+0Po5y02ouz3rz7D4biSJbmiabq6gCs4B5AvM7GTKv4buby7vsAbT9gZ4h0JYmZpXO4YEKeVCk0QkVUlw+uYovE8ibgaVBSLm1Pa3W194rL5/S6/Y7P6/f8vp9SAAAh+QQJAQACACwAAAAAMAAwAAACZZSPqcvtD6OctNqLs968+w+G4kiW5omm6ooALeCusAHHclyzQs3rOz9jAXuqIRFlPJ6SQWRSaIQOpUBqtfjEZpfMJqmrHIFtpbGze2ZywWu0aUwWEbfiZvQdD4sXuWUj7gPos1EAACH5BAkBAAIALAAAAAAwADAAAAJrlI+py+0Po5y02ouz3rz7D4ZiCIxUaU4Amjrr+rDg+7ojXTdyh+e7kPP0egjabGg0EIVImHLJa6KaUam1aqVynNNsUvPTQjO/J84cFA3RzlaJO2495TF63Y7P6/f8vv8PGCg4SFhoeIg4UQAAIfkEBQEAAgAsAAAAADAAMAAAAnaUj6nL7Q+jXGDaW6+GeXsFdFL4UaITnuVBPunKtHGqwoKc0LjN7rdes70QQB/v1ykOj72kMghbPpm51pRKtBaxoteV2SUpsT/Dk0Y+A8lmNZSnZlfH8iy93lzj5+g93+gXKDhIWGh4iJiouMjY6PgIGSk5eVgAADs=";
    d.body.appendChild(z);
    z.className = 'batjs_bat';
    z.id = `bat_${bat_id}`;
    function R(o, m) {
      return Math.max(Math.min(o + (r() - 0.5) * 400, m - 50), 50);
    }
    function A() {
      const batDiv = document.getElementById(`bat_${bat_id}`);
      if (!batDiv) return;
      var x = R(a, w.innerWidth),
        y = R(b, w.innerHeight),
        d = 5 * Math.sqrt((a - x) * (a - x) + (b - y) * (b - y));
      zs.opacity = n;
      n = 1;
      zs.transition = zs.webkitTransition = d / 1e3 + "s linear";
      zs.transform = zs.webkitTransform = "translate(" + x + "px," + y + "px)";
      i.style.transform = i.style.webkitTransform = a > x ? "" : "scaleX(-1)";
      a = x;
      b = y;
      const shouldDelete = batDiv.getAttribute("data-deletion");
      if (shouldDelete) {
        batDiv.style.opacity = 0;
        setTimeout(() => batDiv.remove(), Math.random() * 3e3);
      } else {
        setTimeout(A, d);
      }
    }
    setTimeout(A, r() * 3e3);
  }
};
