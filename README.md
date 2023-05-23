# CS487-Project
Project repo for the course CS-487 Industrial Automation, spring semester 2023, at EPFL.
Group 12: Alexandre Nicolas LECHARTIER, David KWAKYE, Wilhelm WIDLUND MELLERGÅRD, Defne CULHA, Héctor M. RAMIREZ C.

This repo builds on the given sample code https://github.com/phsommer/epfl-cs-487-paint-mixing-plant provided by Philipp Sommer.

The main changes are:
* Extension of the GUI to display current alarms and events
![Extended GUI1](/Documentation/working_op2.png)

* Extension of the GUI to contain a detailed view of a single paint tank
![Extended GUI2](/Documentation/detail_window.png)

* Code framework for random failure of components, resulting in simulation of a faulty plant in operation
* Code framework for detecting component failures via sensor readings, and displaying the resulting alarmsand events in the first GUI extension
![Alarms and events](/Documentation/broken_color_and_valve.png)
In the last image, all paint tank color sensors have failed, as well as the yellow (middle) color tank valve.
