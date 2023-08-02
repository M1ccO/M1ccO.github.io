document.querySelectorAll('.sidebar a').forEach(link => {
  link.addEventListener('click', event => {
    event.preventDefault();
    const id = link.getAttribute('href').substring(1);
    document.querySelectorAll('.content .tabcontent').forEach(tab => {
      tab.style.display = 'none';
    });
    document.getElementById(id).style.display = 'block';
    document.querySelectorAll('.sidebar li').forEach(li => {
      li.classList.remove('active');
    });
    event.target.parentNode.classList.add('active');
  });
});
