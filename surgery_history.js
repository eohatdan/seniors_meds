<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SMA Dashboard</title>
  <link rel="stylesheet" href="styles.css">
  <style>
    /* Basic styles for tabs and content */
    body {
      font-family: Arial, sans-serif;
    }

    .tab {
      overflow: hidden;
      border-bottom: 1px solid #ccc;
      background-color: #f1f1f1;
    }

    .tab button {
      background-color: inherit;
      float: left;
      border: none;
      outline: none;
      cursor: pointer;
      padding: 14px 16px;
      transition: 0.3s;
      font-size: 17px;
    }

    .tab button:hover {
      background-color: #ddd;
    }

    .tab button.active {
      background-color: #ccc;
    }

    .tabcontent {
      display: none;
      padding: 20px;
      border: 1px solid #ccc;
      border-top: none;
    }

    iframe {
      width: 100%;
      height: 600px;
      border: none;
    }
  </style>
</head>
<body>

  <h1>SMA Dashboard</h1>

  <div class="tab">
    <button class="tablinks" onclick="openModule(event, 'HealthRecords')">Health Records</button>
    <button class="tablinks" onclick="openModule(event, 'Medications')">Medications</button>
    <button class="tablinks" onclick="openModule(event, 'SurgeryHistory')">Surgery History</button>
  </div>

  <div id="HealthRecords" class="tabcontent">
    <iframe src="SMA_Health_Records.html" title="Health Records Module"></iframe>
  </div>

  <div id="Medications" class="tabcontent">
    <iframe src="SMA_Medications.html" title="Medications Module"></iframe>
  </div>

  <div id="SurgeryHistory" class="tabcontent">
    <iframe src="SMA_Surgery_History.html" title="Surgery History Module"></iframe>
  </div>

  <script>
    function openModule(evt, moduleName) {
      var i, tabcontent, tablinks;

      // Hide all tab contents
      tabcontent = document.getElementsByClassName("tabcontent");
      for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
      }

      // Remove 'active' class from all tabs
      tablinks = document.getElementsByClassName("tablinks");
      for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
      }

      // Show the selected tab content and set the tab to active
      document.getElementById(moduleName).style.display = "block";
      evt.currentTarget.className += " active";
    }

    // Optionally, open the first tab by default
    document.addEventListener("DOMContentLoaded", function() {
      document.querySelector(".tablinks").click();
    });
  </script>

</body>
</html>
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
