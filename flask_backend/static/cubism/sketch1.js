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

  const pageWidth = window.innerWidth;
  const canvasWidth = pageWidth < 600 ? pageWidth : 600;
  const canvasHeight = canvasWidth;

  const myCanvas = createCanvas(canvasWidth, canvasHeight);
  myCanvas.parent("canvas-container");

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

function mouseClicked() {
  draw();
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
