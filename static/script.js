document.addEventListener('DOMContentLoaded', () => {
    const emotionLabel = document.getElementById('emotion-label');
    const emotionConfidence = document.getElementById('emotion-confidence');
    const emotionRingProgress = document.querySelector('.ring-progress');
    const bpmValue = document.getElementById('bpm-value');
    const rmssdValue = document.getElementById('rmssd-value');
    const rmssdBar = document.getElementById('rmssd-bar');
    const rmssdStatus = document.getElementById('rmssd-status');
    const sdnnValue = document.getElementById('sdnn-value');
    const sdnnStatus = document.getElementById('sdnn-status');
    const statusText = document.getElementById('status-text');

    // === EKG JONLI GRAFIK UCHUN SOZLAMALAR ===
    const ecgCanvas = document.getElementById('ecg-canvas');
    const ctx = ecgCanvas.getContext('2d');
    const MAX_POINTS = 400; // Ekranda nechta nuqta ko'rinishi
    let ecgData = new Array(MAX_POINTS).fill(0);

    function resizeCanvas() {
        if (ecgCanvas.parentElement) {
            ecgCanvas.width = ecgCanvas.parentElement.clientWidth;
            ecgCanvas.height = ecgCanvas.parentElement.clientHeight;
        }
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // Signalni Canvas balandligiga moslash
    function mapValue(val, in_min, in_max, out_min, out_max) {
        return (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
    }

    // Har bir kadrda grafikni chizish
    function drawECG() {
        ctx.clearRect(0, 0, ecgCanvas.width, ecgCanvas.height);
        ctx.beginPath();
        ctx.strokeStyle = '#ff003c'; // Qizil yurak urishi rangi
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';

        const sliceWidth = ecgCanvas.width / MAX_POINTS;
        let x = 0;

        for (let i = 0; i < MAX_POINTS; i++) {
            // Matplotlib'dagi -500 dan 5000 gacha oraliqqa mosladim
            let y = mapValue(ecgData[i], -500, 5000, ecgCanvas.height, 0);

            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
            x += sliceWidth;
        }
        ctx.stroke();
        requestAnimationFrame(drawECG);
    }
    drawECG(); // Chizishni boshlash

    // === WEBSOCKET ALOQASI ===
    const socket = new WebSocket("wss://ekg-emotion-ai.onrender.com/ws"); // Ngrok ishlatsangiz wss:// bilan almashtirasiz

    socket.onopen = () => {
        statusText.textContent = "ALOKA O'RNATILDI";
    };

    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        // 1. Agar signal (sample) kelsa, uni grafik massiviga qo'shamiz
        if (data.type === "sample") {
            ecgData.push(data.value);
            if (ecgData.length > MAX_POINTS) {
                ecgData.shift(); // Eng eskisini o'chiramiz
            }
        }
        
        // 2. Agar tahlil natijasi (result) kelsa, UI elementlarini yangilaymiz
        else if (data.type === "result" || data.bpm !== undefined) {
            if (data.bpm === 0) {
                emotionLabel.textContent = "KUTILMOQDA";
                emotionConfidence.textContent = "0%";
                bpmValue.textContent = "0";
                return;
            }

            emotionLabel.textContent = data.emotion;
            emotionConfidence.textContent = "96%";
            bpmValue.textContent = Math.round(data.bpm);
            rmssdValue.innerHTML = `${Math.round(data.rmssd)}<span class="unit">ms</span>`;
            sdnnValue.innerHTML = `${Math.round(data.sdnn)}<span class="unit">ms</span>`;

            // Vizual elementlarni yangilash
            rmssdBar.style.width = `${Math.min(data.rmssd, 100)}%`;
            rmssdStatus.textContent = data.rmssd < 40 ? 'YUQORI STRESS' : 'OPTIMAL';
            sdnnStatus.textContent = data.sdnn < 50 ? 'NOTURG\'UN' : 'BARQAROR';
            
            // Emotsiyaga qarab rangni o'zgartirish
            let color = '#00ffff'; // Neytral - ko'k
            if (data.emotion === 'STRESS') color = '#ff003c'; // Stress - qizil
            else if (data.emotion === 'XOTIRJAM') color = '#39ff14'; // Xotirjam - yashil
            else if (data.emotion === 'HAYAJON' || data.emotion === 'XURSAND') color = '#b026ff'; // Xursand - binafsha
            
            emotionLabel.style.color = color;
            emotionRingProgress.style.stroke = color;
            emotionRingProgress.style.strokeDashoffset = 100;
        }

        // 3. Status kelganda
        else if (data.type === "status") {
            statusText.textContent = data.text;
        }
    };
});
