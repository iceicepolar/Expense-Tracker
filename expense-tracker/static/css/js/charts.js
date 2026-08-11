// ===============================
// Spending Trend Line Chart
// ===============================

const lineCanvas = document.getElementById("lineChart");

if (lineCanvas) {

    new Chart(lineCanvas, {

        type: "line",

        data: {

            labels: [
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug"
            ],

            datasets: [

                {

                    label: "Expenses",

                    data: [
                        3000,
                        3000,
                        3600,
                        3200,
                        5200,
                        2500
                    ],

                    borderColor: "#d6a33d",

                    backgroundColor: "rgba(214,163,61,.15)",

                    fill: true,

                    tension: .4,

                    borderWidth: 3,

                    pointRadius: 4,

                    pointHoverRadius: 6

                }

            ]

        },

        options: {

            responsive: true,

            maintainAspectRatio: false,

            plugins: {

                legend: {

                    display: false

                }

            },

            scales: {

                x: {

                    grid: {

                        display: false

                    },

                    ticks: {

                        color: "#8b8ea6"

                    }

                },

                y: {

                    grid: {

                        color: "#26263a"

                    },

                    ticks: {

                        color: "#8b8ea6"

                    }

                }

            }

        }

    });

}

// ===============================
// Pie Chart
// ===============================

const pieCanvas = document.getElementById("pieChart");

if (pieCanvas) {

    new Chart(pieCanvas, {

        type: "doughnut",

        data: {

            labels: [

                "Shopping",

                "Food",

                "Transport",

                "Health",

                "Utilities"

            ],

            datasets: [

                {

                    data: [

                        29,

                        23,

                        21,

                        19,

                        8

                    ],

                    backgroundColor: [

                        "#ff5d73",

                        "#4f86ff",

                        "#d6a33d",

                        "#33d69f",

                        "#ff9d42"

                    ],

                    borderWidth: 0

                }

            ]

        },

        options: {

            responsive: true,

            maintainAspectRatio: false,

            cutout: "70%",

            plugins: {

                legend: {

                    position: "bottom",

                    labels: {

                        color: "#d8d8d8",

                        padding: 20

                    }

                }

            }

        }

    });

}