const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const output = document.getElementById("output");
const context = canvas.getContext("2d");

navigator.mediaDevices.getUserMedia({ video: true })
  .then(stream => {
    console.log("✅ Kamera berhasil diakses");
    video.srcObject = stream;
    video.play();
  })
  .catch(err => {
    console.error("❌ Gagal akses kamera:", err);
  });

async function sendFrame() {
  try {
    // render video ke canvas
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    // konversi canvas ke blob
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg"));

    if (!blob) {
      console.error("❌ Canvas kosong, tidak ada frame yang dikirim!");
      return;
    }

    const formData = new FormData();
    formData.append("frame", blob, "frame.jpg");

    const response = await fetch("/detect_api", {
      method: "POST",
      body: formData
    });

    console.log("📡 Status response:", response.status);

    if (!response.ok) throw new Error("HTTP " + response.status);

    const blobResp = await response.blob();

    if (blobResp.size > 0) {
      console.log("✅ Frame hasil YOLO diterima, size:", blobResp.size);
      const objectUrl = URL.createObjectURL(blobResp);
      output.src = objectUrl;

      // bebaskan memory setelah image selesai load
      output.onload = () => URL.revokeObjectURL(objectUrl);
    }
  } catch (err) {
    console.error("❌ Error kirim frame:", err);
  }
}

// mulai setelah video siap
video.addEventListener("loadeddata", () => {
  // YOLO butuh waktu proses → jangan terlalu cepat, 1 detik sekali cukup
  setInterval(sendFrame, 1000);
});
