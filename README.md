# boost-container-pretty-printer

Put this in your $(HOME)/.gdbinit file with proper path to pretty printers:

```python
  
  python
  import sys 
  sys.path.insert(0, 'YOUR_PATH_HERE/boost-container-pretty-printer')
  from printers import register_boost_container_printers
  register_boost_container_printers (None)
  end
```  
