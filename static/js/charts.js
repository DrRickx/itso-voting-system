document.addEventListener("DOMContentLoaded", function () {
  const ctx = document.getElementById("partylistChart");
  if (!ctx) return;

  const names = window.partylistNames || [];
  const votes = window.partylistVotes || [];

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: names,
      datasets: [{
        label: 'Votes',
        data: votes,
        backgroundColor: 'rgba(54,162,235,0.6)'
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } }
    }
  });
});
