import pytest

from reviewpanel.models import Program, Form, FormBlock, CustomBlock, FormLabel


# this is really just test-data creation, with a little testing on the side

@pytest.fixture(scope='session')
def program(db_no_rollback):
    p = Program(name='Co-Prosperity')
    p.save()
    yield p

def test_program(program):
    assert program

@pytest.fixture(scope='session')
def program_form(program):
    f = Form(program=program, name='Exhibitions Application 2022')
    f.save()
    yield f

def test_program_form(program_form):
    assert program_form

@pytest.fixture(scope='session')
def stock_name_block(program_form):
    b = FormBlock(form=program_form, name='name', options={'type': 'name'})
    b.save()
    yield b
    
def test_stock_block(stock_name_block):
    assert stock_name_block

@pytest.fixture(scope='session')
def stock_email_block(program_form, stock_name_block):
    b = FormBlock(form=program_form, name='contact', options={'type': 'email'},
                  rank=1)
    b.save()
    yield b

def test_stock_email_block(stock_email_block):
    assert stock_email_block

@pytest.fixture(scope='session')
def custom_text_block(program_form, stock_email_block):
    b = CustomBlock(form=program_form, name='response', page=2,
                    type=CustomBlock.InputType.TEXT,
                    min_chars=1, max_chars=1000, num_lines=5)
    b.save()
    yield b

def test_custom_text_block(custom_text_block):
    assert custom_text_block

@pytest.fixture(scope='session')
def custom_choice_block(program_form, custom_text_block):
    b = CustomBlock(form=program_form, name='type', page=2, rank=1,
                    type=CustomBlock.InputType.CHOICE, required=True,
                    options={'choices': ['foo', 'bar', 'baz']})
    b.save()
    yield b

def test_custom_choice_block(custom_choice_block):
    assert custom_choice_block

@pytest.fixture(scope='session')
def custom_boolean_block(program_form, custom_choice_block):
    b = CustomBlock(form=program_form, name='optin', page=2, rank=2,
                    type=CustomBlock.InputType.BOOLEAN)
    b.save()
    yield b

def test_custom_boolean_block(custom_boolean_block):
    assert custom_boolean_block

def test_publish_form(program_form, custom_boolean_block):
    program_form.publish()
    assert program_form.status == Form.Status.ENABLED

@pytest.fixture(scope='session')
def altered_label(program_form, custom_boolean_block):
    path = custom_boolean_block.name
    label = FormLabel.objects.get(form=program_form, path=path)

    label.text = 'Sign up for our mailing list'
    label.save()
    yield label

def test_altered_label(altered_label):
    assert altered_label
