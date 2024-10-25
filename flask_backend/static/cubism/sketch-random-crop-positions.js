let payload;
let imgUrls = [];
let images = [];
let squares = [];

let squareWidth;
let squareHeight;

let loadedImages = 0;
let allImagesLoaded = false;

function prepSquares() {
  for (const img of images) {
    img.resize(width, height);
    img.loadPixels();

    for (let y = 0; y < height; y += squareHeight) {
      for (let x = 0; x < width; x += squareWidth) {
        const imgCrop = img.get(x, y, squareWidth, squareHeight);
        squares.push(imgCrop);
      }
    }
  }
}

function prepImage(_img) {
  loadedImages++;
  if (loadedImages == imgUrls.length) {
    allImagesLoaded = true;
    prepSquares();
    draw();
  }
}

function preload() {
  payload = loadJSON("/movies/posters/images/urls");
}

function setup() {
  const cols = 4;
  const rows = 4;

  const pageWidth = document
    .getElementById("canvas-container")
    .getBoundingClientRect().width;
  const canvasWidth = pageWidth < 500 ? pageWidth : 500;
  const canvasHeight = canvasWidth * 1.6;

  const myCanvas = createCanvas(canvasWidth, canvasHeight);
  myCanvas.parent("canvas-container");
  myCanvas.mouseClicked(_mouseClicked);

  background(89);

  squareWidth = width / cols;
  squareHeight = height / rows;

  imgUrls = Object.values(payload);

  for (let i = 0; i < imgUrls.length; i++) {
    const path = imgUrls[i];
    images.push(loadImage(path, prepImage));
  }
  noLoop();
}

function _mouseClicked() {
  draw();
  if (window.goatcounter) {
    window.goatcounter.count({
      path: window.location.pathname,
      title: "Cubism random crop positions click",
      event: true,
    });
  }
}

function draw() {
  if (!allImagesLoaded) return;
  background(89);
  squares = shuffle(squares);
  let x = 0;
  let y = 0;

  for (const square of squares) {
    image(square, x, y);
    x += squareWidth;
    if (x >= width) {
      x = 0;
      y += squareHeight;
    }
  }
}
