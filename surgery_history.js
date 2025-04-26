const SURGERY_HISTORY_KEY = 'surgeryHistory';
let surgeries = [];

function loadSurgeries() {
  const storedData = localStorage.getItem(SURGERY_HISTORY_KEY);
  surgeries = storedData ? JSON.parse(storedData) : [];
  renderTable();
}

function saveSurgeries() {
  localStorage.setItem(SURGERY_HISTORY_KEY, JSON.stringify(surgeries));
}

function renderTable() {
  const tbody = document.querySelector('#surgeryTable tbody');
  tbody.innerHTML = '';
  surgeries.forEach((surgery, index) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${surgery.surgery_name}</td>
      <td>${surgery.surgery_date}</td>
      <td>${surgery.surgeon_name}</td>
      <td>${surgery.surgery_hospital}</td>
      <td>
        <button onclick="editSurgery(${index})">Edit</button>
        <button onclick="deleteSurgery(${index})">Delete</button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

function addSurgery() {
  const surgery_name = prompt('Enter Surgery Name:');
  const surgery_date = prompt('Enter Surgery Date (YYYY-MM-DD):');
  const surgeon_name = prompt('Enter Surgeon Name:');
  const surgery_hospital = prompt('Enter Surgery Hospital:');
  if (surgery_name && surgery_date && surgeon_name && surgery_hospital) {
    surgeries.push({ surgery_name, surgery_date, surgeon_name, surgery_hospital });
    saveSurgeries();
    renderTable();
  }
}

function editSurgery(index) {
  const surgery = surgeries[index];
  const surgery_name = prompt('Edit Surgery Name:', surgery.surgery_name);
  const surgery_date = prompt('Edit Surgery Date (YYYY-MM-DD):', surgery.surgery_date);
  const surgeon_name = prompt('Edit Surgeon Name:', surgery.surgeon_name);
  const surgery_hospital = prompt('Edit Surgery Hospital:', surgery.surgery_hospital);
  if (surgery_name && surgery_date && surgeon_name && surgery_hospital) {
    surgeries[index] = { surgery_name, surgery_date, surgeon_name, surgery_hospital };
    saveSurgeries();
    renderTable();
  }
}

function deleteSurgery(index) {
  if (confirm('Are you sure you want to delete this surgery record?')) {
    surgeries.splice(index, 1);
    saveSurgeries();
    renderTable();
  }
}

document.addEventListener('DOMContentLoaded', loadSurgeries);
