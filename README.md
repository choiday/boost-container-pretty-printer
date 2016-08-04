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
If you're using windows - visual studio 2010 then, you could use autoexp.dat which is located in the Program Files\Microsoft Visual Studio 11.0\Common7\Packages\Debugger directory.
