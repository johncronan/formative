
document.querySelectorAll('.rp-choiceset-textinput')
        .forEach(row => {
  let control = row.firstElementChild.querySelector('input');
  let textInput = row.querySelector('.rp-text-field input');
  control.onchange = evt => {
    if (!evt.target.checked) textInput.value = '';
  };
  textInput.oninput = evt => {
    if (evt.target.value) {
      control.checked = true;
      if (control.type == 'radio') {
        row.parentElement.firstElementChild.querySelectorAll('input')
           .forEach(radio => radio.checked = false);
      }
    }
  };
  
  if (control.type == 'radio') {
    row.parentElement.firstElementChild.querySelectorAll('input')
       .forEach(radio => radio.onchange = evt => {
         if (evt.target.checked) {
           control.checked = false;
           textInput.value = '';
       }
    });
  }
});
