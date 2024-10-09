let payload;
let imgUrls = [];
let images = [];
let squares = [];
let squareGrid = [];

let squareWidth;
let squareHeight;

let loadedImages = 0;
let allImagesLoaded = false;

let cols = 4;
let rows = 4;

function prepSquares() {
  for (const img of images) {
    let grid = [];
    img.resize(width, height);
    img.loadPixels();
    for (let y = 0; y < height; y += squareHeight) {
      let row = [];
      for (let x = 0; x < width; x += squareWidth) {
        row.push(img.get(x, y, squareWidth, squareHeight));
      }
      grid.push(row);
    }
    squareGrid.push(grid);
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
}

function draw() {
  if (!allImagesLoaded) return;
  background(89);

  let x = 0;
  let y = 0;

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      let randomImageIndex = floor(random(squareGrid.length));
      let square = squareGrid[randomImageIndex][row][col];
      image(square, x, y);
      x += squareWidth;
    }
    x = 0;
    y += squareHeight;
  }
}
