import {MDCRipple} from '@material/ripple/index';
import {MDCTopAppBar} from '@material/top-app-bar';
import {MDCFormField} from '@material/form-field';
import {MDCTextField} from '@material/textfield';
import {MDCTextFieldCharacterCounter}
    from '@material/textfield/character-counter';
import {MDCNotchedOutline} from '@material/notched-outline';
import {MDCRadio} from '@material/radio';
import {MDCCheckbox} from '@material/checkbox';
import {MDCDataTable} from '@material/data-table';
import {MDCTooltip} from '@material/tooltip';

import Sortable from 'sortablejs';

import axios from 'axios';
axios.defaults.xsrfHeaderName = "X-CSRFToken";

import "./stock/address.js";
import "./stock/choiceset.js";

const appBar = new MDCTopAppBar(document.querySelector('.mdc-top-app-bar'));

const texts = [];
document.querySelectorAll('.mdc-text-field')
        .forEach(text => {
           var t = new MDCTextField(text);
           texts.push(t);
           if (text.classList.contains('rp-text-field--invalid')) {
               t.useNativeValidation = false;
               t.valid = false;
           }
        });

const counters = [];
document.querySelectorAll('.mdc-text-field-character-counter')
        .forEach(c => counters.push(new MDCTextFieldCharacterCounter(c)));

const outlines = [];
document.querySelectorAll('.mdc-notched-outline')
        .forEach(outline => outlines.push(new MDCNotchedOutline(outline)));

const radios = [];
document.querySelectorAll('.mdc-radio')
        .forEach(radio => radios.push(new MDCRadio(radio)));

const checkboxes = [];
document.querySelectorAll('.mdc-checkbox')
        .forEach(checkbox => checkboxes.push(new MDCCheckbox(checkbox)));

const formFields = [];
//document.querySelectorAll('.mdc-form-field')
//       .forEach(field => formFields.push(new MDCFormField('.mdc-form-field')))

// TODO: set formField.input = radio, for ripple?

//const dataTables = [];
//document.querySelectorAll('.mdc-data-table')
//        .forEach(table => dataTables.push(new MDCDataTable(table)));

const ripples = [];
document.querySelectorAll('.mdc-button,.mdc-button-icon')
        .forEach(button => ripples.push(new MDCRipple(button)));

const tooltips = [];
document.querySelectorAll('.mdc-tooltip')
        .forEach(tip => tooltips.push(new MDCTooltip(tip)));

function errorMessage(err, msg) {
  if (err.response && err.response.status >= 500)
    return (msg ? msg + ': ' : '') + 'server error';
  return (msg ? msg + ': ' : '') + 'communication error';
}

function pageError() {
  var bottom = document.querySelector('#rp-page-error');
  bottom.parentElement.style.display = 'block';
  bottom.firstElementChild.innerHTML = 'Page needs to be reloaded.';
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  for (let i=0; i < sortables.length; i++) sortables[i].option('sort', false);
}

function setError(rowEl, err, msg) {
  setStatus(rowEl, 'error');
  var td = rowEl.querySelector('td.rp-item-message-cell');
  if (!td) td = rowEl.querySelector('td:last-child');
  td.firstElementChild.innerHTML = errorMessage(err, msg);
  pageError();
}

function itemMove(rowEl, rank) {
  var itemId = rowEl.dataset.id;
  var url = postUrlBase();
  
  var data = new FormData();
  data.append('item_id', itemId);
  data.append('rank', rank);
  axios.post(url + '/moveitem', data, { timeout: 10000 })
    .catch(err => {
        setError(rowEl, err);
    });
}

document.addEventListener('dragover', function(e) { e.preventDefault() });

const sortables = [];
document.querySelectorAll('.rp-collection-table-body')
        .forEach(tbody => sortables.push(Sortable.create(tbody, {
          animation: 120,
          handle: '.rp-sort-handle-cell',
          filter: '.rp-collection-field-errors',
          onMove: e => {
            return !e.related.classList.contains('rp-collection-field-errors');
          },
          onEnd: event => {
            var itemRow = event.item;
            if (event.oldIndex != event.newIndex) {
              if (!itemRow.querySelector('.rp-sort-defer'))
                itemMove(itemRow, event.newIndex + 1);
              else {
                let tbody = itemRow.parentElement;
                for (let i=0; i < tbody.children.length; i++) {
                  let tr = tbody.children[i];
                  tr.querySelector('.rp-hidden-rank-input').value = i;
                }
              }
            }
          }
        })));

function postUrlBase() {
  var href = document.location.href;
  var url = href.substring(0, href.lastIndexOf('/'));
  return url;
}

const filesQueue = [];
const simultaneous = 4;

function postFile(rowEl, file) {
  var itemId = rowEl.dataset.id
  var url = postUrlBase();
  var data = new FormData();
  data.append('item_id', itemId);
  data.append('file', file);
  
  var config = {
    onUploadProgress: event => {
      var percentCompleted = Math.round((event.loaded * 100) / event.total);
      var progress = rowEl.querySelector('.rp-progress-bar');
      var bar = progress.firstElementChild;
      bar.style.width = percentCompleted + '%';
      bar.firstElementChild.innerHTML = percentCompleted.toFixed(0) + '%';
    }
  };
  
  axios.post(url + '/file', data, config)
    .then(res => {
      if (!res.data) setStatus(rowEl, 'normal');
      else {
        rowEl.querySelector('span.rp-item-error').innerHTML = res.data;
        setStatus(rowEl, 'error');
      }
      
      for (let i=0; i < filesQueue.length; i++) {
        if (filesQueue[i][1].dataset.id == rowEl.dataset.id) {
          filesQueue.splice(i, 1);
          break;
        }
      }
      if (!filesQueue.length)
        document.querySelectorAll('.rp-save-button,.rp-continue-button')
                .forEach(button => button.disabled = false);
      processQueue();
    })
    .catch(err => {
      setError(rowEl, err, 'upload failed');
    });
}

function processQueue() {
  for (let i=0; i < filesQueue.length; i++) {
    if (i >= simultaneous) break;
    if (!filesQueue[i][0]) {
      filesQueue[i][0] = true;
      postFile(filesQueue[i][1], filesQueue[i][2]);
    }
  }
}

function uploadFile(rowEl, file) {
  filesQueue.push([false, rowEl, file]);
  document.querySelectorAll('.rp-save-button,.rp-continue-button')
          .forEach(button => button.disabled = true);
}

function rowStatus(rowEl) {
  if (rowEl.querySelector('td.rp-item-progress-cell').style.display != 'none')
    return 'upload';
  if (rowEl.querySelector('td.rp-item-message-cell').style.display != 'none')
    return 'error';
  return 'normal';
}

function setStatus(rowEl, status) {
  var hide, show, upload='';
  if (rowEl.dataset.fileOptional) upload=',td.rp-item-upload-action';
  if (status == 'normal') {
    hide = 'td.rp-item-progress-cell,td.rp-item-message-cell';
    show = 'td.rp-item-field-cell' + upload;
  } else if (status == 'error') {
    hide = 'td.rp-item-progress-cell,td.rp-item-field-cell';
    show = 'td.rp-item-message-cell,td.rp-item-upload-action';
  }
  rowEl.querySelectorAll(hide).forEach(row => row.style.display = 'none');
  rowEl.querySelectorAll(show).forEach(row => row.style.display = 'table-cell');
}

function updateTotal(blockId, incr) {
  var prefix = 'input[name="items' + blockId;
  var n = parseInt(document.querySelector(prefix + '-TOTAL_FORMS"]').value);
  document.querySelector(prefix + '-TOTAL_FORMS"]').value = n + incr;
  document.querySelector(prefix + '-INITIAL_FORMS"]').value = n + incr;
}

function newItems(blockId, restore, files, itemId) {
  var url = postUrlBase();
  
  var data = new FormData();
  data.append('block_id', blockId);
  if (itemId) data.append('item_id', itemId);
  
  var haveFile;
  var filesArray = [];
  if (files) for (let i=0; i < files.length; i++) {
    data.append('filesize' + files[i].size, files[i].name);
    filesArray.push(files[i]);
    haveFile = true;
  }
  
  axios.post(url + '/item', data, { timeout: 20000 })
    .then(res => {
      var table = document.querySelector('#collection' + blockId);
      var tablediv = table.parentElement.parentElement;
      var tbody = table.firstElementChild;
      var rows = [];
      
      if (itemId) {
        var itemEl = tbody.querySelector('tr[data-id="' + itemId + '"]');
        itemEl.innerHTML = res.data.trim();
        rows = [itemEl];
      } else {
        var tablePos = tbody.querySelector('tr:last-child');
        var html = res.data.trim();
        var prevNum = tbody.children.length;
        if (!tablePos) {
          tbody.innerHTML = html;
          tablediv.style.display = 'flex';
          rows = tbody.querySelectorAll('tr');
        } else {
          var isErr = tablePos.classList.contains('rp-collection-field-errors');
          if (isErr) prevNum -= 1;
          var prevPos = isErr ? tablePos.previousElementSibling : tablePos;
          tablePos.insertAdjacentHTML(isErr ? 'beforebegin' : 'afterend', html);
          let element = prevPos || tbody.querySelector('tr:first-child');
          while (element = element.nextElementSibling) {
            if (!element.classList.contains('rp-collection-field-errors'))
                rows.push(element);
          }
        }
        
        updateTotal(blockId, rows.length);
        var numRows = prevNum + rows.length;
        
        var maxItems = table.dataset.maxItems;
        var sel = '.rp-collection-button[data-block-id="' + blockId + '"]';
        if (numRows >= maxItems) document.querySelector(sel).disabled = true;
      }
      
      if (haveFile) for (let i=0; i < rows.length; i++) {
        if (rowStatus(rows[i]) == 'upload') uploadFile(rows[i], filesArray[i]);
      }
      processQueue();
      
      unsaved = restore;
      document.querySelectorAll('.rp-item-upload')
              .forEach(button => button.onclick = uploadClick);
      document.querySelectorAll('.rp-item-remove')
              .forEach(button => button.onclick = removeClick);
      document.querySelectorAll('.mdc-text-field')
              .forEach(text => {
        var t = new MDCTextField(text);
        if (text.classList.contains('rp-text-field--invalid')) {
          t.useNativeValidation = false;
          t.valid = false;
        }
      });
    })
    .catch(err => {
      var table = document.querySelector('#collection' + blockId);
      var tbody = table.firstElementChild;
      var tr = tbody.firstElementChild;
      var span = 0;
      if (tr) {
        let element = tr.firstElementChild;
        span = element.colSpan;
        while (element = element.nextElementSibling) {
          span += element.colSpan;
        }
      }
      if (!span) span = 1;
      var errRow = document.createElement('tr');
      var msg = errorMessage(err);
      errRow.innerHTML = '<td class="mdc-data-table__cell" ' +
        'style="height: 48px;"></td><td class="mdc-data-table__cell" ' +
        'colspan="' + span + '"><span class="rp-item-error">' + msg +
        '</span></td>';
      tbody.appendChild(errRow);
      table.parentElement.parentElement.style.display = 'flex';
      pageError();
    });
}

function filesSelected(event, blockId, restore, itemId) {
  var fileInput = event.target;
  if (fileInput.files.length)
    newItems(blockId, restore, fileInput.files, itemId);
  fileInput.value = '';
  fileInput.style.display = 'none';
}

function collectionClick(event) {
  var buttonEl = event.target;
  if (buttonEl.parentElement.tagName.toLowerCase() == 'button')
    buttonEl = buttonEl.parentElement;
  var blockId = buttonEl.dataset.blockId;
  var restore = unsaved;
  
  if (buttonEl.dataset.needsFile) {
    var fileInput = document.querySelector('input[name="file' + blockId + '"]');
    fileInput.onchange = event => filesSelected(event, blockId, restore);
    
    // opacity and width zero will have to do, while we're working with it
    fileInput.style.display = 'inline-block';
    fileInput.click();
  } else {
    newItems(blockId, restore);
  }
}

document.querySelectorAll('.rp-collection-button')
        .forEach(button => button.onclick = collectionClick);

function uploadClick(event) {
  var rowEl = event.target.parentElement.parentElement;
  var blockId = rowEl.dataset.blockId;
  var id = rowEl.dataset.id;
  var fileInput = document.querySelector('input[name="itemfile' + id + '"]');
  var restore = unsaved;
  fileInput.onchange = event => filesSelected(event, blockId, restore, id);
  fileInput.style.display = 'inline-block';
  fileInput.click();
}

document.querySelectorAll('.rp-item-upload')
        .forEach(button => button.onclick = uploadClick);

function removeClick(event) {
  var url = postUrlBase();
  var rowEl = event.target.parentElement.parentElement;
  var blockId = rowEl.dataset.blockId;
  var id = rowEl.dataset.id;
  
  var data = new FormData();
  data.append('item_id', id);
  axios.post(url + '/removeitem', data, { timeout: 10000 })
    .then(res => {
      var tbody = rowEl.parentElement;
      var restore = unsaved;
      tbody.removeChild(rowEl);
      updateTotal(blockId, -1);
      
      var numRows = tbody.children.length;
      var table = tbody.parentElement;
      if (!numRows) {
        var tablediv = table.parentElement.parentElement;
        tablediv.style.display = 'none';
      }
      var maxItems = table.dataset.maxItems;
      if (numRows < maxItems) {
        var sel = '.rp-collection-button[data-block-id="' + blockId + '"]';
        document.querySelector(sel).disabled = false;
      }
      unsaved = restore;
    })
    .catch(err => {
      setError(rowEl, err);
    });
}

document.querySelectorAll('.rp-item-remove')
        .forEach(button => button.onclick = removeClick);


window.addEventListener("pageshow", function() {
  document.querySelectorAll('.rp-text-field--invalid')
          .forEach(text => text.classList.add('mdc-text-field--invalid'));
  
  texts.forEach(text => { if (text.value) text.value = text.value; });
});

var unsaved = false, submitting = false;
var form = document.querySelector('form#submission');

if (form) {
  document.querySelectorAll('.rp-item-field input')
          .forEach(input => {
    input.oninvalid = (e) => {
      var td = e.target.parentElement.parentElement;
      if (td.style.display == 'none') {
        e.target.required = false;
        form.submit();
        return false;
      }
    };
  });
  
  form.onchange = () => {
    unsaved = true;
  };
  form.onsubmit = () => {
    submitting = true;
  }

  window.onbeforeunload = (event) => {
    var msg = "There are unsaved changes on this page.";
    if (unsaved && !submitting) return msg;
  };
}
