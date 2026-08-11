// ===============================
// Dashboard charts — data comes from the server, not hardcoded
// ===============================

(function () {
  const payload = document.getElementById("chartData");
  if (!payload || typeof Chart === "undefined") return;

  let data;
  try {
    data = JSON.parse(payload.textContent);
  } catch (error) {
    console.error("Could not read chart data", error);
    return;
  }

  const GRID = "#26263a";
  const TICK = "#8b8ea6";

  // ---------------------------------------------------------------
  // Income vs spending, last six months
  // ---------------------------------------------------------------

  const lineCanvas = document.getElementById("lineChart");

  if (lineCanvas) {
    new Chart(lineCanvas, {
      type: "line",

      data: {
        labels: data.trend.labels,

        datasets: [
          {
            label: "Spent",
            data: data.trend.expenses,
            borderColor: "#d6a33d",
            backgroundColor: "rgba(214,163,61,.15)",
            fill: true,
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
          {
            label: "Income",
            data: data.trend.income,
            borderColor: "#3ddc97",
            backgroundColor: "rgba(61,220,151,.12)",
            fill: true,
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
        ],
      },

      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },

        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: { color: "#d8d8d8", boxWidth: 12, usePointStyle: true },
          },
        },

        scales: {
          x: {
            grid: { display: false },
            ticks: { color: TICK },
          },
          y: {
            beginAtZero: true,
            grid: { color: GRID },
            ticks: {
              color: TICK,
              // Keep the axis readable on narrow phones
              callback: function (value) {
                return value >= 1000 ? value / 1000 + "k" : value;
              },
            },
          },
        },
      },
    });
  }

  // ---------------------------------------------------------------
  // Spending by category
  // ---------------------------------------------------------------

  const pieCanvas = document.getElementById("pieChart");

  if (pieCanvas && data.categories.values.length) {
    new Chart(pieCanvas, {
      type: "doughnut",

      data: {
        labels: data.categories.labels,

        datasets: [
          {
            data: data.categories.values,
            backgroundColor: data.categories.colors,
            borderWidth: 0,
          },
        ],
      },

      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",

        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: "#d8d8d8",
              padding: 14,
              boxWidth: 12,
              usePointStyle: true,
            },
          },
        },
      },
    });
  }
})();
