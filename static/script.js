const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const output = document.getElementById("output");
const context = canvas.getContext("2d");

navigator.mediaDevices.getUserMedia({ video: true })
  .then(stream => {
    video.srcObject = stream;
  })
  .catch(err => {
    console.error("Gagal akses kamera:", err);
  });

setInterval(() => {
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(blob => {
    const formData = new FormData();
    formData.append("frame", blob, "frame.jpg");

    fetch("/detect_api", {
      method: "POST",
      body: formData
    })
    .then(response => response.blob())
    .then(blob => {
      output.src = URL.createObjectURL(blob);
    })
    .catch(err => console.error("Error:", err));
  }, "image/jpeg");
}, 5000); 
